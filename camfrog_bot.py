#!/usr/bin/env python3
"""Camfrog bot main process with calibrated UIA coordinates, VB-Cable TTS, Active-Speaker tracking,
enhanced 5.1/5.2 SQLite database schema (`users`, `chat_history`, `user_activity`, `chat_sessions`,
`message_analysis`, plus backward-compatible `bot_users`/`bot_messages`/`mic_grabs`/`moderation_events`),
and all 20 KaeKae_Toad triggers.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import logging
import random
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
    EDGE_TTS_DEFAULT_VOICE,
    EDGE_TTS_VOICES,
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
from ui_automation import (
    COQUI_DEFAULT_VOICE,
    COQUI_FEMALE_VOICES,
    CamfrogUIAutomation,
    clean_username,
)


LOG = logging.getLogger("camfrog_bot")
_WORD_RE = re.compile(r"[A-Za-z][A-Za-z'-]{2,}")

# Common English stopwords / pronouns / verbs / prepositions excluded when computing "top NOUN used"
_NON_NOUN_STOPWORDS: set[str] = {
    "the", "and", "for", "that", "this", "with", "you", "your", "are", "was", "were", "have", "has",
    "had", "not", "but", "what", "all", "can", "her", "his", "him", "she", "they", "them", "their",
    "from", "out", "about", "who", "get", "got", "just", "like", "know", "how", "when", "where",
    "why", "would", "could", "should", "will", "there", "here", "been", "into", "more", "some",
    "than", "then", "now", "only", "also", "very", "too", "much", "many", "well", "back", "even",
    "still", "way", "our", "one", "two", "see", "saw", "did", "does", "doing", "done", "make",
    "made", "take", "took", "come", "came", "going", "went", "want", "said", "say", "says",
    "really", "right", "yeah", "yes", "nah", "nope", "lol", "lmao", "rofl", "omg", "wtf", "idk",
    "dont", "don't", "cant", "can't", "im", "i'm", "ive", "i've", "its", "it's", "youre", "you're",
    "thats", "that's", "whats", "what's", "let", "lets", "hey", "hello", "good", "great", "nice",
    "cool", "sure", "okay", "never", "always", "every", "other", "another", "same", "such",
    "over", "under", "again", "after", "before", "because", "while", "through", "between",
}

_POSITIVE_WORDS: set[str] = {
    "love", "great", "awesome", "amazing", "good", "nice", "happy", "win", "won", "jackpot",
    "sweet", "cool", "best", "thanks", "thank", "haha", "lol", "lmao", "fun", "glad", "fire",
    "goat", "legend", "blessed", "boom", "congrats", "hella", "lit",
}
_NEGATIVE_WORDS: set[str] = {
    "hate", "bad", "mad", "angry", "sad", "lost", "lose", "bust", "busted", "stupid", "dumb",
    "trash", "rigged", "annoying", "wtf", "damn", "sucks", "worst", "broke", "ugly", "fake",
    "boring", "tired", "sick", "cry",
}

_FEMALE_NAME_HINTS: set[str] = {
    "rosie", "queen", "princess", "girl", "lady", "mama", "bella", "sarah", "jess", "ashley",
    "angel", "barbie", "babe", "kitten", "goddess", "vixen", "diva", "bunny", "peach", "chica",
    "emily", "chloe", "mia", "ava", "aria", "jenny", "lisa", "amy", "katie", "amber", "nikki",
    "tiffany", "crystal", "brandy", "mandi", "mandy", "samantha", "rachel", "rebecca", "lauren",
}
_MALE_NAME_HINTS: set[str] = {
    "wayne", "stonerwayne", "king", "boy", "guy", "bro", "dude", "man", "mr", "sir", "lord",
    "daddy", "papa", "mike", "john", "dave", "chris", "matt", "josh", "ryan", "kevin", "brian",
    "jason", "justin", "brandon", "tyler", "adam", "alex", "dan", "nick", "tony", "mark",
    "paul", "steven", "steve", "ken", "rob", "bob", "bill", "joe", "tom", "jim", "tim", "jay",
}

# Pool of 50+ unique, witty, never-repeated disses for !diss <username> / !diss the room
_UNIQUE_DISS_TEMPLATES: tuple[str, ...] = (
    "{target}, your comeback is still buffering on 1998 dial-up while your confidence arrived on fiber optic.",
    "{target}, if brains were PAT tokens you wouldn't even have enough to trigger a !beg cooldown.",
    "{target}, I've seen sharper takes from the Wheel of Misfortune landing on bankrupt six times in a row.",
    "{target}, your keyboard must be filing for workers' comp after carrying all that nonsense in chat.",
    "{target}, you type like someone who brings a lockpick to a convenience store heist and still trips the alarm.",
    "{target}, even Camfrog's lurkers scrolled past your message just to protect their eyesight.",
    "{target}, your mic presence has the same energy as a lawnmower starting up at 6 AM on a Sunday.",
    "{target}, if charisma were a D&D stat on your !sheet, yours would still be waiting for a reroll.",
    "{target}, you're the reason the casino vault keeps its doors unlocked—they know you'll still whiff the roll.",
    "{target}, I checked your profile in my SQLite database and even the indexes refused to optimize it.",
    "{target}, your chat history reads like a fortune cookie written by a confused goblin.",
    "{target}, I've heard clearer audio coming from a drive-thru speaker during a thunderstorm.",
    "{target}, you bring 'unspent stat points' energy to every conversation in Players__Lounge.",
    "{target}, if wit were currency, you'd be spamming !beg every three hours on the dot.",
    "{target}, even my backup OCR engine squinted at your last line and said 'nah, skip that.'",
    "{target}, you talk like you've got Kingpin's Ring equipped, but you roll like a level 1 decoy.",
    "{target}, the room's IQ goes up by 12 points every time your typing indicator disappears.",
    "{target}, your hot takes need a patch note, a hotfix, and a full server rollback.",
    "{target}, you're proof that autoplay can happen in real life without a brain attached.",
    "{target}, I'd roast you harder, but Camfrog has a strict policy against smoking low-tier loot.",
    "{target}, your vibe is 10% Mastermind and 90% getting caught at Round 1 of the store robbery.",
    "{target}, even VB-Cable tried to mute itself when it heard your name come up.",
    "{target}, you've got the comedic timing of a 180-second random spin landing on a skull.",
    "{target}, if we put your best comebacks in a vault, nobody would bother forming a crew to rob it.",
    "{target}, you're like a human captcha—nobody understands what you're doing here, and everyone wants to skip.",
    "{target}, I ran sentiment analysis on your messages and the database just returned 'bless their heart.'",
    "{target}, your typing style is what happens when autocomplete gives up and walks out.",
    "{target}, you've got champagne confidence on a !beg handout budget.",
    "{target}, even a 4-pixel Camfrog indicator pane has more presence in this room than that last comment.",
    "{target}, if overconfidence paid out PAT, you'd have capped the 5,000,000 jackpot pool by yourself.",
    "{target}, I asked the magic conch about your next message and it told me to hit !shutup.",
    "{target}, your chat game is like buying 1 ticket in !lotto and already planning your retirement speech.",
    "{target}, you're the human equivalent of forgetting to press the Talk button while giving a 5-minute speech.",
    "{target}, I've seen bots from 2004 AIM chatrooms with smoother conversation skills.",
    "{target}, your roasts hit like a foam noodle in an Arena battle royale.",
    "{target}, every time you grab the mic, three lurkers suddenly remember they have laundry to fold.",
    "{target}, your strategy in chat is all gas, no brakes, and zero steering wheel.",
    "{target}, if we auctioned off your best takes in the heist shop, they'd cost 0 PAT and still go unsold.",
    "{target}, you're out here playing 4D chess against yourself and still losing in three moves.",
    "{target}, even my suppression vault said 'please don't dump that in here.'",
)

_MOD_RE = re.compile(
    r"^\s*(?P<actor>[A-Za-z0-9_$.\-\[\]@~^]{2,32})\s+(?:was\s+)?"
    r"(?P<action>unpunished|unblocked|unbanned|punished|blocked|banned|kicked)\s+"
    r"(?P<target>[A-Za-z0-9_$.\-\[\]@~^]{2,32})(?:\s+microphone)?\s*[.!]?\s*$",
    re.IGNORECASE,
)
_MOD_BY_RE = re.compile(
    r"^\s*(?P<target>[A-Za-z0-9_$.\-\[\]@~^]{2,32})\s+was\s+"
    r"(?P<action>unpunished|unblocked|unbanned|punished|blocked|banned|kicked)\s+by\s+"
    r"(?P<actor>[A-Za-z0-9_$.\-\[\]@~^]{2,32})\s*[.!]?\s*$",
    re.IGNORECASE,
)
# Trigger 16: Moderation History Queries (Chat or Spoken on Mic):
# who kicked [username], who blocked/unblocked [username], who banned/unbanned [username], who punished/unpunished [username]
# Must NOT fire unless there is a valid username after the trigger words!
_HISTORY_RE = re.compile(
    r"^(?:kaekae[\s,:]+)?who\s+(?P<action>kicked|blocked|unblocked|banned|unbanned|punished|unpunished)"
    r"\s+(?P<target>[A-Za-z0-9_$.\-\[\]@~^]{2,32})\s*\??$",
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


def analyze_sentiment_and_tone(text: str) -> tuple[float, str]:
    """Compute a sentiment score (-1.0 to +1.0) and human-readable tone label for a message or transcript."""
    words = [w.casefold() for w in _WORD_RE.findall(str(text or ""))]
    if not words:
        return 0.0, "neutral"
    pos = sum(1 for w in words if w in _POSITIVE_WORDS)
    neg = sum(1 for w in words if w in _NEGATIVE_WORDS)
    exclam = str(text or "").count("!")
    quest = str(text or "").count("?")
    score = (pos - neg) / float(max(1, pos + neg + 1))
    if score >= 0.25:
        tone = "upbeat/positive" if exclam == 0 else "excited/hyped"
    elif score <= -0.25:
        tone = "salty/critical" if exclam == 0 else "heated/fiery"
    elif quest >= 1:
        tone = "inquisitive/curious"
    elif exclam >= 2:
        tone = "energetic/expressive"
    else:
        tone = "conversational/chill"
    return round(score, 3), tone


def extract_top_noun(texts: Iterable[str]) -> tuple[str, int]:
    """Extract the top NOUN used across a user's messages (filtering stopwords, commands, verbs, and pronouns)."""
    counts: Counter[str] = Counter()
    for raw in texts:
        cleaned = re.sub(r"^\[MIC\]\s*", "", str(raw or ""), flags=re.I)
        if cleaned.startswith("!"):
            continue
        for word in _WORD_RE.findall(cleaned):
            low = word.casefold()
            if len(low) < 3 or low in _NON_NOUN_STOPWORDS or low == BOT_USERNAME.casefold():
                continue
            counts[low] += 1
    if not counts:
        # Fallback to any word if all words were in the stopword list
        fallback = Counter(
            w.casefold()
            for raw in texts
            for w in _WORD_RE.findall(re.sub(r"^\[MIC\]\s*", "", str(raw or ""), flags=re.I))
        )
        return fallback.most_common(1)[0] if fallback else ("n/a", 0)
    return counts.most_common(1)[0]


def infer_user_gender(username: str, messages: Iterable[str] = (), color_hint: str = "unknown") -> str:
    """Identify user gender: Blue = male, Pink = female, plus self-identification or username heuristics."""
    if color_hint in {"male", "female"}:
        return color_hint
    low_u = str(username or "").casefold()
    for hint in _FEMALE_NAME_HINTS:
        if hint in low_u:
            return "female (pink)"
    for hint in _MALE_NAME_HINTS:
        if hint in low_u:
            return "male (blue)"
    joined = " ".join(str(m or "").casefold() for m in messages)
    if re.search(r"\b(i am a girl|i'm a girl|im a woman|female here|as a woman|my husband|my bf)\b", joined):
        return "female (pink)"
    if re.search(r"\b(i am a guy|i'm a guy|im a man|male here|my wife|my gf)\b", joined):
        return "male (blue)"
    return "unknown"


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
    """Enhanced 5.1/5.2 SQLite persistence with:
    - `users` table (extended with `is_active`, `first_join_time`, `gender`, `status_category`, `speech_patterns`, `biography`)
    - `chat_history` table with sentiment analysis capabilities
    - `user_activity` table for detailed tracking (join, quit, mic_grab, spin, command)
    - `chat_sessions` table for session management
    - `message_analysis` table for text & noun analysis
    - Backward-compatible `bot_users`, `bot_messages`, `presence_events`, `moderation_events`, `mic_grabs`, `suppressed_users`
    - Optimized composite indexes across all frequently queried columns.
    """

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
                -- Legacy & Core tables
                CREATE TABLE IF NOT EXISTS bot_users (
                    username TEXT PRIMARY KEY COLLATE NOCASE,
                    first_seen TEXT NOT NULL,
                    last_seen TEXT NOT NULL,
                    message_count INTEGER NOT NULL DEFAULT 0,
                    active INTEGER NOT NULL DEFAULT 1,
                    joined_at TEXT NOT NULL DEFAULT '',
                    total_chat_seconds REAL NOT NULL DEFAULT 0,
                    gender TEXT NOT NULL DEFAULT 'unknown',
                    status_category TEXT NOT NULL DEFAULT 'member',
                    speech_patterns TEXT NOT NULL DEFAULT '',
                    biography TEXT NOT NULL DEFAULT ''
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

                -- 5.1 & 5.2 Enhanced Database Schema Tables
                CREATE TABLE IF NOT EXISTS users (
                    username TEXT PRIMARY KEY COLLATE NOCASE,
                    is_active INTEGER NOT NULL DEFAULT 1,
                    first_join_time TEXT NOT NULL,
                    last_seen_time TEXT NOT NULL,
                    gender TEXT NOT NULL DEFAULT 'unknown',
                    user_status TEXT NOT NULL DEFAULT 'member',
                    message_count INTEGER NOT NULL DEFAULT 0,
                    mic_grab_count INTEGER NOT NULL DEFAULT 0,
                    total_mic_seconds REAL NOT NULL DEFAULT 0.0,
                    total_chat_seconds REAL NOT NULL DEFAULT 0.0,
                    top_noun TEXT NOT NULL DEFAULT 'n/a',
                    text_tone TEXT NOT NULL DEFAULT 'neutral',
                    audio_tone TEXT NOT NULL DEFAULT 'neutral',
                    speech_patterns TEXT NOT NULL DEFAULT '',
                    biography TEXT NOT NULL DEFAULT ''
                );

                CREATE TABLE IF NOT EXISTS chat_history (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    event_key TEXT UNIQUE NOT NULL,
                    username TEXT NOT NULL COLLATE NOCASE,
                    message_text TEXT NOT NULL,
                    source_type TEXT NOT NULL DEFAULT 'chat',
                    sentiment_score REAL NOT NULL DEFAULT 0.0,
                    detected_tone TEXT NOT NULL DEFAULT 'neutral',
                    room_time TEXT NOT NULL DEFAULT '',
                    observed_at TEXT NOT NULL
                );

                CREATE TABLE IF NOT EXISTS user_activity (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    username TEXT NOT NULL COLLATE NOCASE,
                    activity_type TEXT NOT NULL,
                    activity_detail TEXT NOT NULL DEFAULT '',
                    duration_seconds REAL NOT NULL DEFAULT 0.0,
                    observed_at TEXT NOT NULL
                );

                CREATE TABLE IF NOT EXISTS chat_sessions (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    username TEXT NOT NULL COLLATE NOCASE,
                    session_start TEXT NOT NULL,
                    session_end TEXT NOT NULL DEFAULT '',
                    duration_seconds REAL NOT NULL DEFAULT 0.0,
                    is_open INTEGER NOT NULL DEFAULT 1
                );

                CREATE TABLE IF NOT EXISTS message_analysis (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    username TEXT NOT NULL COLLATE NOCASE,
                    message_text TEXT NOT NULL,
                    top_noun_candidate TEXT NOT NULL DEFAULT '',
                    word_count INTEGER NOT NULL DEFAULT 0,
                    sentiment_score REAL NOT NULL DEFAULT 0.0,
                    tone_label TEXT NOT NULL DEFAULT 'neutral',
                    analyzed_at TEXT NOT NULL
                );

                -- 5.2.2 Optimized Composite Indexes for high-speed user lookups and chat history searches
                CREATE INDEX IF NOT EXISTS idx_bot_messages_user_time ON bot_messages(username, observed_at);
                CREATE INDEX IF NOT EXISTS idx_moderation_target_time ON moderation_events(target, observed_at);
                CREATE INDEX IF NOT EXISTS idx_users_active_seen ON users(is_active, last_seen_time);
                CREATE INDEX IF NOT EXISTS idx_chat_history_user_time ON chat_history(username, observed_at);
                CREATE INDEX IF NOT EXISTS idx_user_activity_user_type_time ON user_activity(username, activity_type, observed_at);
                CREATE INDEX IF NOT EXISTS idx_chat_sessions_user_open ON chat_sessions(username, is_open, session_start);
                CREATE INDEX IF NOT EXISTS idx_message_analysis_user_time ON message_analysis(username, analyzed_at);
                CREATE INDEX IF NOT EXISTS idx_mic_grabs_user_started ON mic_grabs(username, started_at);
                """
            )
            # Ensure existing SQLite databases gain all extended columns cleanly
            for ddl in (
                "ALTER TABLE bot_users ADD COLUMN joined_at TEXT NOT NULL DEFAULT ''",
                "ALTER TABLE bot_users ADD COLUMN total_chat_seconds REAL NOT NULL DEFAULT 0",
                "ALTER TABLE bot_users ADD COLUMN gender TEXT NOT NULL DEFAULT 'unknown'",
                "ALTER TABLE bot_users ADD COLUMN status_category TEXT NOT NULL DEFAULT 'member'",
                "ALTER TABLE bot_users ADD COLUMN speech_patterns TEXT NOT NULL DEFAULT ''",
                "ALTER TABLE bot_users ADD COLUMN biography TEXT NOT NULL DEFAULT ''",
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
        """Trigger 7 (!suppress): Dump all user data into a separate JSON folder (`data/suppressed_users`) and delete from active tables."""
        username = clean_username(username)
        if not username or self.is_suppressed(username):
            return False
        with self._session() as db:
            user = db.execute("SELECT * FROM bot_users WHERE username = ?", (username,)).fetchone()
            ext_user = db.execute("SELECT * FROM users WHERE username = ?", (username,)).fetchone()
            messages = db.execute("SELECT * FROM bot_messages WHERE username = ? ORDER BY id", (username,)).fetchall()
            chat_hist = db.execute("SELECT * FROM chat_history WHERE username = ? ORDER BY id", (username,)).fetchall()
            activities = db.execute("SELECT * FROM user_activity WHERE username = ? ORDER BY id", (username,)).fetchall()
            sessions = db.execute("SELECT * FROM chat_sessions WHERE username = ? ORDER BY id", (username,)).fetchall()
            analyses = db.execute("SELECT * FROM message_analysis WHERE username = ? ORDER BY id", (username,)).fetchall()
            grabs = db.execute("SELECT * FROM mic_grabs WHERE username = ? ORDER BY id", (username,)).fetchall()
            payload = {
                "username": username,
                "suppressed_at": now_iso(),
                "user": dict(user) if user else None,
                "ext_user": dict(ext_user) if ext_user else None,
                "messages": [dict(row) for row in messages],
                "chat_history": [dict(row) for row in chat_hist],
                "user_activity": [dict(row) for row in activities],
                "chat_sessions": [dict(row) for row in sessions],
                "message_analysis": [dict(row) for row in analyses],
                "mic_grabs": [dict(row) for row in grabs],
            }
            vault = self.suppressed_dir / f"{username.casefold()}.json"
            vault.write_text(json.dumps(payload, indent=2), encoding="utf-8")
            for tbl in ("bot_messages", "mic_grabs", "bot_users", "users", "chat_history", "user_activity", "chat_sessions", "message_analysis"):
                db.execute(f"DELETE FROM {tbl} WHERE username = ?", (username,))
            db.execute(
                "INSERT INTO suppressed_users(username, suppressed_at, vault_file) VALUES (?, ?, ?)",
                (username, payload["suppressed_at"], str(vault)),
            )
        return True

    def unsuppress(self, username: str) -> bool:
        """Trigger 8 (!unsuppress): Pull the dumped data from the separate folder back into all active database tables."""
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
                        username, first_seen, last_seen, message_count, active, joined_at, total_chat_seconds,
                        gender, status_category, speech_patterns, biography
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                    (
                        user["username"],
                        user["first_seen"],
                        user["last_seen"],
                        user["message_count"],
                        user["active"],
                        user.get("joined_at", ""),
                        float(user.get("total_chat_seconds", 0.0)),
                        user.get("gender", "unknown"),
                        user.get("status_category", "member"),
                        user.get("speech_patterns", ""),
                        user.get("biography", ""),
                    ),
                )
            ext_user = payload.get("ext_user")
            if ext_user:
                db.execute(
                    """INSERT OR REPLACE INTO users(
                        username, is_active, first_join_time, last_seen_time, gender, user_status,
                        message_count, mic_grab_count, total_mic_seconds, total_chat_seconds,
                        top_noun, text_tone, audio_tone, speech_patterns, biography
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                    (
                        ext_user["username"],
                        ext_user.get("is_active", 1),
                        ext_user.get("first_join_time", now_iso()),
                        ext_user.get("last_seen_time", now_iso()),
                        ext_user.get("gender", "unknown"),
                        ext_user.get("user_status", "member"),
                        ext_user.get("message_count", 0),
                        ext_user.get("mic_grab_count", 0),
                        float(ext_user.get("total_mic_seconds", 0.0)),
                        float(ext_user.get("total_chat_seconds", 0.0)),
                        ext_user.get("top_noun", "n/a"),
                        ext_user.get("text_tone", "neutral"),
                        ext_user.get("audio_tone", "neutral"),
                        ext_user.get("speech_patterns", ""),
                        ext_user.get("biography", ""),
                    ),
                )
            for message in payload.get("messages", []):
                db.execute(
                    "INSERT OR IGNORE INTO bot_messages(event_key, username, body, observed_at, room_time) VALUES (?, ?, ?, ?, ?)",
                    (message["event_key"], message["username"], message["body"], message["observed_at"], message["room_time"]),
                )
            for ch in payload.get("chat_history", []):
                db.execute(
                    """INSERT OR IGNORE INTO chat_history(
                        event_key, username, message_text, source_type, sentiment_score, detected_tone, room_time, observed_at
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
                    (
                        ch["event_key"],
                        ch["username"],
                        ch["message_text"],
                        ch.get("source_type", "chat"),
                        float(ch.get("sentiment_score", 0.0)),
                        ch.get("detected_tone", "neutral"),
                        ch.get("room_time", ""),
                        ch["observed_at"],
                    ),
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
            db.execute("UPDATE bot_users SET active = 0")
            db.execute("UPDATE users SET is_active = 0")
            for raw in usernames:
                user = clean_username(raw)
                if not user or self.is_suppressed(user):
                    continue
                gender_guess = infer_user_gender(user)
                existing = db.execute(
                    "SELECT joined_at, active, gender FROM bot_users WHERE username = ?",
                    (user,),
                ).fetchone()
                if existing is None:
                    db.execute(
                        """INSERT INTO bot_users(
                            username, first_seen, last_seen, message_count, active, joined_at, total_chat_seconds, gender
                        ) VALUES (?, ?, ?, 0, 1, ?, 0, ?)""",
                        (user, observed_at, observed_at, observed_at, gender_guess),
                    )
                else:
                    joined_at = existing["joined_at"] or observed_at
                    g_val = existing["gender"] if existing["gender"] not in {"", "unknown"} else gender_guess
                    db.execute(
                        "UPDATE bot_users SET last_seen = ?, active = 1, joined_at = ?, gender = ? WHERE username = ?",
                        (observed_at, joined_at, g_val, user),
                    )
                db.execute(
                    """INSERT INTO users(username, is_active, first_join_time, last_seen_time, gender, user_status)
                    VALUES (?, 1, ?, ?, ?, 'member')
                    ON CONFLICT(username) DO UPDATE SET
                        is_active = 1,
                        last_seen_time = excluded.last_seen_time,
                        gender = CASE WHEN users.gender = 'unknown' THEN excluded.gender ELSE users.gender END""",
                    (user, observed_at, observed_at, gender_guess),
                )
                seeded += 1
                if seeded >= MAX_ROOM_USERS:
                    break
        return seeded

    def update_user_attributes(
        self,
        username: str,
        *,
        gender: str | None = None,
        status_category: str | None = None,
    ) -> None:
        username = clean_username(username)
        if not username or self.is_suppressed(username):
            return
        with self._session() as db:
            if gender and gender != "unknown":
                db.execute("UPDATE bot_users SET gender = ? WHERE username = ?", (gender, username))
                db.execute("UPDATE users SET gender = ? WHERE username = ?", (gender, username))
            if status_category:
                db.execute("UPDATE bot_users SET status_category = ? WHERE username = ?", (status_category, username))
                db.execute("UPDATE users SET user_status = ? WHERE username = ?", (status_category, username))

    def record_message(self, username: str, body: str, room_time: str, *, mark_active: bool = True) -> None:
        username = clean_username(username)
        if not username or self.is_suppressed(username):
            return
        observed_at = now_iso()
        effective_time = room_time or (f"{observed_at}:{time.monotonic():.4f}" if mark_active else "")
        key = message_key(username, body, effective_time)
        joined_val = observed_at if mark_active else ""
        sentiment_score, tone_label = analyze_sentiment_and_tone(body)
        is_mic = str(body or "").startswith("[MIC]")
        source_type = "mic_transcript" if is_mic else "chat"
        top_noun_cand, _ = extract_top_noun([body])
        word_cnt = len(_WORD_RE.findall(body))
        gender_guess = infer_user_gender(username, [body])

        with self._session() as db:
            inserted = db.execute(
                "INSERT OR IGNORE INTO bot_messages(event_key, username, body, observed_at, room_time) VALUES (?, ?, ?, ?, ?)",
                (key, username, body, observed_at, room_time),
            ).rowcount
            if inserted:
                if mark_active:
                    db.execute(
                        """INSERT INTO bot_users(username, first_seen, last_seen, message_count, active, joined_at, total_chat_seconds, gender)
                        VALUES (?, ?, ?, 1, 1, ?, 0, ?)
                        ON CONFLICT(username) DO UPDATE SET
                            last_seen=excluded.last_seen,
                            message_count=bot_users.message_count + 1,
                            active=1,
                            gender=CASE WHEN bot_users.gender = 'unknown' THEN excluded.gender ELSE bot_users.gender END,
                            joined_at=CASE WHEN bot_users.joined_at = '' THEN excluded.joined_at ELSE bot_users.joined_at END""",
                        (username, observed_at, observed_at, joined_val, gender_guess),
                    )
                else:
                    db.execute(
                        """INSERT INTO bot_users(username, first_seen, last_seen, message_count, active, joined_at, total_chat_seconds, gender)
                        VALUES (?, ?, ?, 1, 0, '', 0, ?)
                        ON CONFLICT(username) DO UPDATE SET
                            last_seen=excluded.last_seen,
                            gender=CASE WHEN bot_users.gender = 'unknown' THEN excluded.gender ELSE bot_users.gender END,
                            message_count=bot_users.message_count + 1""",
                        (username, observed_at, observed_at, gender_guess),
                    )

                # Populate 5.1/5.2 Enhanced Tables: chat_history, message_analysis, user_activity, users
                db.execute(
                    """INSERT OR IGNORE INTO chat_history(
                        event_key, username, message_text, source_type, sentiment_score, detected_tone, room_time, observed_at
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
                    (key, username, body, source_type, sentiment_score, tone_label, room_time, observed_at),
                )
                db.execute(
                    """INSERT INTO message_analysis(
                        username, message_text, top_noun_candidate, word_count, sentiment_score, tone_label, analyzed_at
                    ) VALUES (?, ?, ?, ?, ?, ?, ?)""",
                    (username, body, top_noun_cand, word_cnt, sentiment_score, tone_label, observed_at),
                )
                db.execute(
                    """INSERT INTO user_activity(username, activity_type, activity_detail, duration_seconds, observed_at)
                    VALUES (?, ?, ?, 0.0, ?)""",
                    (username, source_type, body[:200], observed_at),
                )
                db.execute(
                    """INSERT INTO users(
                        username, is_active, first_join_time, last_seen_time, gender, user_status,
                        message_count, top_noun, text_tone, audio_tone
                    ) VALUES (?, ?, ?, ?, ?, 'member', 1, ?, ?, ?)
                    ON CONFLICT(username) DO UPDATE SET
                        is_active = CASE WHEN ? = 1 THEN 1 ELSE users.is_active END,
                        last_seen_time = excluded.last_seen_time,
                        message_count = users.message_count + 1,
                        gender = CASE WHEN users.gender = 'unknown' THEN excluded.gender ELSE users.gender END,
                        top_noun = CASE WHEN excluded.top_noun != 'n/a' THEN excluded.top_noun ELSE users.top_noun END,
                        text_tone = CASE WHEN ? = 'chat' THEN excluded.text_tone ELSE users.text_tone END,
                        audio_tone = CASE WHEN ? = 'mic_transcript' THEN excluded.audio_tone ELSE users.audio_tone END""",
                    (
                        username,
                        1 if mark_active else 0,
                        observed_at,
                        observed_at,
                        gender_guess,
                        top_noun_cand,
                        tone_label,
                        tone_label,
                        1 if mark_active else 0,
                        source_type,
                        source_type,
                    ),
                )

    def record_presence(self, username: str, action: str, event_key: str) -> None:
        """Record Join: or Quit: from the Chat Window and update chat_sessions, user_activity, users, and bot_users."""
        username = clean_username(username)
        if not username or self.is_suppressed(username):
            return
        observed_at = now_iso()
        gender_guess = infer_user_gender(username)
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
                            username, first_seen, last_seen, message_count, active, joined_at, total_chat_seconds, gender
                        ) VALUES (?, ?, ?, 0, 1, ?, 0, ?)""",
                        (username, observed_at, observed_at, observed_at, gender_guess),
                    )
                else:
                    db.execute(
                        "UPDATE bot_users SET last_seen = ?, active = 1, joined_at = ? WHERE username = ?",
                        (observed_at, observed_at, username),
                    )
                db.execute(
                    """INSERT INTO users(username, is_active, first_join_time, last_seen_time, gender)
                    VALUES (?, 1, ?, ?, ?)
                    ON CONFLICT(username) DO UPDATE SET is_active = 1, last_seen_time = excluded.last_seen_time""",
                    (username, observed_at, observed_at, gender_guess),
                )
                db.execute(
                    "INSERT INTO chat_sessions(username, session_start, is_open) VALUES (?, ?, 1)",
                    (username, observed_at),
                )
                db.execute(
                    "INSERT INTO user_activity(username, activity_type, activity_detail, duration_seconds, observed_at) VALUES (?, 'join', 'Joined room', 0.0, ?)",
                    (username, observed_at),
                )
            else:  # action == "quit"
                elapsed = 0.0
                if existing is None:
                    db.execute(
                        """INSERT INTO bot_users(
                            username, first_seen, last_seen, message_count, active, joined_at, total_chat_seconds, gender
                        ) VALUES (?, ?, ?, 0, 0, '', 0, ?)""",
                        (username, observed_at, observed_at, gender_guess),
                    )
                else:
                    elapsed = _seconds_between_iso(existing["joined_at"] or "", observed_at)
                    new_total = float(existing["total_chat_seconds"] or 0.0) + elapsed
                    db.execute(
                        "UPDATE bot_users SET last_seen = ?, active = 0, joined_at = '', total_chat_seconds = ? WHERE username = ?",
                        (observed_at, new_total, username),
                    )
                db.execute(
                    """INSERT INTO users(username, is_active, first_join_time, last_seen_time, total_chat_seconds, gender)
                    VALUES (?, 0, ?, ?, ?, ?)
                    ON CONFLICT(username) DO UPDATE SET
                        is_active = 0,
                        last_seen_time = excluded.last_seen_time,
                        total_chat_seconds = users.total_chat_seconds + ?""",
                    (username, observed_at, observed_at, elapsed, gender_guess, elapsed),
                )
                db.execute(
                    "UPDATE chat_sessions SET session_end = ?, duration_seconds = ?, is_open = 0 WHERE username = ? AND is_open = 1",
                    (observed_at, elapsed, username),
                )
                db.execute(
                    "INSERT INTO user_activity(username, activity_type, activity_detail, duration_seconds, observed_at) VALUES (?, 'quit', 'Left room', ?, ?)",
                    (username, elapsed, observed_at),
                )

    def record_moderation(self, event: dict[str, str], raw_text: str) -> None:
        key = message_key(event["actor"], f"{event['action']}:{event['target']}:{raw_text}")
        observed_at = now_iso()
        with self._session() as db:
            db.execute(
                "INSERT OR IGNORE INTO moderation_events(event_key, actor, target, action, observed_at, raw_text) VALUES (?, ?, ?, ?, ?, ?)",
                (key, event["actor"], event["target"], event["action"], observed_at, raw_text),
            )
            db.execute(
                "INSERT INTO user_activity(username, activity_type, activity_detail, duration_seconds, observed_at) VALUES (?, 'moderation', ?, 0.0, ?)",
                (event["target"], f"{event['action']} by {event['actor']}", observed_at),
            )

    def record_mic_grab(self, username: str, started_at: str, duration_seconds: float, transcript: str = "") -> None:
        username = clean_username(username)
        if not username or self.is_suppressed(username):
            return
        dur = float(duration_seconds)
        clean_tx = str(transcript or "").strip()
        _, audio_tone = analyze_sentiment_and_tone(clean_tx) if clean_tx else (0.0, "spoken/active")
        with self._session() as db:
            db.execute(
                "INSERT INTO mic_grabs(username, started_at, duration_seconds, transcript) VALUES (?, ?, ?, ?)",
                (username, started_at, dur, clean_tx),
            )
            db.execute(
                "INSERT INTO user_activity(username, activity_type, activity_detail, duration_seconds, observed_at) VALUES (?, 'mic_grab', ?, ?, ?)",
                (username, clean_tx[:200] or "Microphone broadcast", dur, started_at),
            )
            db.execute(
                """INSERT INTO users(username, is_active, first_join_time, last_seen_time, mic_grab_count, total_mic_seconds, audio_tone)
                VALUES (?, 1, ?, ?, 1, ?, ?)
                ON CONFLICT(username) DO UPDATE SET
                    last_seen_time = excluded.last_seen_time,
                    mic_grab_count = users.mic_grab_count + 1,
                    total_mic_seconds = users.total_mic_seconds + ?,
                    audio_tone = CASE WHEN ? != '' THEN excluded.audio_tone ELSE users.audio_tone END""",
                (username, started_at, started_at, dur, audio_tone, dur, clean_tx),
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
            messages = db.execute(
                "SELECT body FROM bot_messages WHERE username = ? ORDER BY id DESC LIMIT 40",
                (username,),
            ).fetchall()
            mic_rows = db.execute(
                "SELECT duration_seconds, transcript, started_at FROM mic_grabs WHERE username = ? ORDER BY id DESC LIMIT 20",
                (username,),
            ).fetchall()
            msg_bodies = [row["body"] for row in messages]
            chat_only = [b for b in msg_bodies if not str(b).startswith("[MIC]")]
            mic_transcripts = [row["transcript"] for row in mic_rows if row["transcript"]] + [
                str(b)[5:].strip() for b in msg_bodies if str(b).startswith("[MIC]")
            ]

            # Raw word frequency (kept as top_word for backward compatibility with existing unit test)
            words = Counter(word.casefold() for b in msg_bodies for word in _WORD_RE.findall(b))
            top_word, top_count = words.most_common(1)[0] if words else ("n/a", 0)

            # Top NOUN used (excluding stopwords/pronouns/commands)
            top_noun, top_noun_count = extract_top_noun(msg_bodies)

            # Text tone & Audio tone
            _, text_tone = analyze_sentiment_and_tone(" ".join(chat_only[:15])) if chat_only else (0.0, "quiet/observer")
            if mic_transcripts:
                _, audio_tone = analyze_sentiment_and_tone(" ".join(mic_transcripts[:10]))
            elif mic_rows:
                audio_tone = "vocal/active on mic"
            else:
                audio_tone = "silent (no mic grabs)"

            user_dict = dict(user)
            gender = infer_user_gender(
                str(user_dict["username"]),
                msg_bodies,
                color_hint=str(user_dict.get("gender") or "unknown"),
            )
            chat_seconds = float(user_dict.get("total_chat_seconds") or 0.0)
            if user_dict.get("active") and user_dict.get("joined_at"):
                chat_seconds += _seconds_between_iso(str(user_dict["joined_at"]), now_iso())

            avg_words = (
                sum(len(_WORD_RE.findall(b)) for b in chat_only) / float(len(chat_only))
                if chat_only
                else 0.0
            )
            speech_style = (
                "rapid short bursts"
                if 0 < avg_words < 4.5
                else ("detailed storyteller" if avg_words >= 9.0 else "conversational")
            )
            bio_summary = (
                f"{user_dict['username']} ({gender}, {'currently in room' if user_dict.get('active') else 'offline'}) "
                f"has logged {user_dict['message_count']} lines ({speech_style}, {text_tone} text tone, "
                f"{audio_tone} mic vibe, favorite noun '{top_noun}')."
            )
            # Persist enriched biography, speech patterns, and top noun into `users` & `bot_users`
            db.execute(
                "UPDATE bot_users SET gender = ?, speech_patterns = ?, biography = ? WHERE username = ?",
                (gender, speech_style, bio_summary, user_dict["username"]),
            )
            db.execute(
                """UPDATE users SET gender = ?, top_noun = ?, text_tone = ?, audio_tone = ?,
                   speech_patterns = ?, biography = ? WHERE username = ?""",
                (gender, top_noun, text_tone, audio_tone, speech_style, bio_summary, user_dict["username"]),
            )

            return {
                **user_dict,
                "gender": gender,
                "messages": msg_bodies[:20],
                "mic_transcripts": mic_transcripts[:10],
                "top_word": top_word,
                "top_count": top_count,
                "top_noun": top_noun,
                "top_noun_count": top_noun_count,
                "text_tone": text_tone,
                "audio_tone": audio_tone,
                "speech_patterns": speech_style,
                "biography": bio_summary,
                "chat_duration_seconds": chat_seconds,
            }

    def mic_stats(self, username: str | None, seconds: int) -> tuple[int, float]:
        cutoff = datetime.fromtimestamp(time.time() - seconds, timezone.utc).isoformat(timespec="seconds")
        query = "SELECT COUNT(*), COALESCE(SUM(duration_seconds), 0) FROM mic_grabs WHERE started_at >= ?"
        args: tuple[object, ...] = (cutoff,)
        if username:
            query += " AND username = ? COLLATE NOCASE"
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
    """Main UIA monitor, initial roster + Join/Quit tracker, VB-Cable TTS broadcaster, live mic transcriber, and command dispatcher."""

    def __init__(
        self,
        *,
        dry_run: bool = False,
        automation: CamfrogUIAutomation | None = None,
        store: CamfrogStore | None = None,
        log_callback: object = None,
    ):
        LOG_DIR.mkdir(parents=True, exist_ok=True)
        logging.basicConfig(filename=LOG_DIR / "bot.log", level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
        self.ui_automation = automation or CamfrogUIAutomation()
        self.store = store or CamfrogStore()
        self.dry_run = dry_run
        self.settings = dict(BOT_SETTINGS)
        self.running = False
        self._seen: set[str] = set()
        self._recent_messages: deque[tuple[str, str]] = deque(maxlen=CHAT_HISTORY_LIMIT)
        self._recent_transcripts: deque[tuple[str, str, str]] = deque(maxlen=40)
        self._pages: dict[str, deque[str]] = {}
        self._diss_jobs: dict[str, float] = {}
        self._used_disses: set[str] = set()
        self._queued_broadcasts: deque[str] = deque()
        self._current_speaker: str | None = None
        self._speaker_started_iso: str = ""
        self._speaker_started_mono: float = 0.0
        self._current_speaker_chunks: list[str] = []
        self._transcribe_busy: bool = False
        self._last_transcribe_mono: float = 0.0
        self._last_mingle_mono: float = 0.0
        self._log_cb = log_callback
        self.initial_users: list[str] = []

    def _emit_bot_log(self, msg: str) -> None:
        LOG.info("%s", msg)
        if callable(self._log_cb):
            try:
                self._log_cb(msg)
            except Exception:
                pass

    def _self_notice(self, msg: str) -> None:
        """Log an internal functional/status notice to the OPERATOR terminals ONLY.

        KaeKae_Toad NEVER posts these to the live room chat (per operator request), so she does not
        chatter about her own functions or settings, and there is zero risk of echoing/looping into a live
        room. Use this for all status/setting confirmations (!chat, !transcribe, !admin, !triggers, etc.).
        """
        self._emit_bot_log(f"[KAEKAE-NOTICE 🔒] {msg}")

    def initialize(self, *, mark_existing_seen: bool = True) -> bool:
        already_connected = bool(getattr(self.ui_automation, "is_connected", lambda: False)())
        if not already_connected and not self.ui_automation.connect_to_camfrog():
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
        self._queued_broadcasts.clear()
        self._diss_jobs.clear()
        LOG.warning("Kill switch requested.")

    def silent_switch(self, enabled: bool | None = None) -> bool:
        if enabled is None:
            enabled = not self.settings["silent_mode"]
        self.settings["silent_mode"] = bool(enabled)
        if self.settings["silent_mode"]:
            self._queued_broadcasts.clear()
            self._diss_jobs.clear()
        return self.settings["silent_mode"]

    def _apply_tone(self, message: str) -> str:
        """Apply KaeKae_Toad's active tone (!happy, !sad, !mad) when !chat mode is ON."""
        if not self.settings.get("chat_mode"):
            return message
        tone = str(self.settings.get("tone", "neutral")).lower()
        if tone == "happy":
            return f"✨😊 {message} 💖"
        if tone == "sad":
            return f"🌧️😔 *sigh*... {message} 💔"
        if tone == "mad":
            return f"🔥😤 LISTEN UP: {message} 💢"
        return message

    def _event_key(self, event: dict[str, str]) -> str:
        return message_key(event.get("user", ""), f"{event.get('kind', '')}:{event.get('action', '')}:{event.get('text', '')}", event.get("timestamp", ""))

    def _spawn_speaker_transcribe_worker(self, speaker_name: str) -> None:
        """Capture and transcribe a 2.8s audio slice for the identified active speaker on a background thread.
        - ALWAYS prints live speech transcriptions and audio capture diagnostics directly to the front of Terminal 1!
        - Silently records speech to the SQLite database for user profiles/biographies by default.
        - When `!transcribe` is turned ON (`post_transcripts_to_chat=True`), ALSO posts `[MIC] <Speaker>: <Text>` in real time to Camfrog chat.
        - Also checks if spoken audio contained a Moderation History query (`who kicked <username>`, etc.).
        """
        if self._transcribe_busy or not self.settings.get("transcription_mode", True):
            return
        if not hasattr(self.ui_automation, "transcribe_audio_chunk_for_speaker"):
            return

        import threading

        self._transcribe_busy = True
        self._last_transcribe_mono = time.monotonic()

        def _worker() -> None:
            try:
                try:
                    raw_res = self.ui_automation.transcribe_audio_chunk_for_speaker(
                        duration_seconds=2.8, return_details=True
                    )
                except TypeError:
                    raw_res = self.ui_automation.transcribe_audio_chunk_for_speaker(duration_seconds=2.8)

                if isinstance(raw_res, dict):
                    transcript = str(raw_res.get("transcript", "") or "").strip()
                    dev_name = str(raw_res.get("device_name", "Input"))
                    peak_val = int(raw_res.get("peak", 0))
                    eng_name = str(raw_res.get("engine", "SpeechEngine"))
                    err_note = str(raw_res.get("error", "") or "")
                else:
                    transcript = str(raw_res or "").strip()
                    dev_name = "AudioInput"
                    peak_val = 250 if transcript else 0
                    eng_name = "GoogleWebSpeech"
                    err_note = ""

                active_spk = self._current_speaker or speaker_name
                if transcript and self.running:
                    cleaned_t = transcript.strip()
                    if not self.store.is_suppressed(active_spk):
                        self._current_speaker_chunks.append(cleaned_t)
                        ts_now = now_iso()
                        self._recent_transcripts.append((ts_now, active_spk, cleaned_t))
                        # Save spoken words into speaker's profile in SQLite DB
                        self.store.record_message(active_spk, f"[MIC] {cleaned_t}", ts_now)
                        # Route the real-time spoken transcript (with user info + what they are saying)
                        # straight to Terminal 3 (Dedicated Live Transcription) via the [LIVE-TRANSCRIBE] tag.
                        self._emit_bot_log(
                            f"[LIVE-TRANSCRIBE 📝] [MIC] {active_spk}: \"{cleaned_t}\" "
                            f"(Device='{dev_name}', Peak={peak_val}, Engine={eng_name})"
                        )
                        # Trigger 5: When !transcribe is ON, also post [MIC] <Speaker>: <Text> in real time to Camfrog chat
                        if self.settings.get("post_transcripts_to_chat", False) and not self.settings.get("silent_mode", False):
                            self.send_reply(active_spk, f"[MIC] {active_spk}: {cleaned_t}")
                        # Trigger 16: Support Spoken Moderation History Queries ("who kicked <username>", etc.)
                        spoken_hist = _HISTORY_RE.match(cleaned_t)
                        if spoken_hist and not self.settings.get("silent_mode", False):
                            for rep in self._history_reply(
                                active_spk,
                                spoken_hist.group("action").lower(),
                                spoken_hist.group("target"),
                            ):
                                self.send_reply(active_spk, rep)
                elif self.running and active_spk:
                    # Show live audio diagnostic reaction in Terminal 1 so the user knows the mic listener is active
                    if peak_val < 35:
                        self._emit_bot_log(
                            f"[INCOMING MIC AUDIO 🎧] Listening to '{active_spk}' on '{dev_name}' "
                            f"(Peak={peak_val} — low/silent audio; verify Camfrog speaker output feeds VB-Cable or Stereo Mix)"
                        )
                    else:
                        self._emit_bot_log(
                            f"[INCOMING MIC AUDIO 🎧] Captured '{active_spk}' audio slice on '{dev_name}' "
                            f"(Peak={peak_val}, no clear words recognized{': ' + err_note if err_note else ''})"
                        )
            except Exception as exc:
                LOG.debug("Transcribe worker note: %s", exc)
            finally:
                self._transcribe_busy = False

        threading.Thread(target=_worker, name="KaeKaeLiveTranscriber", daemon=True).start()

    def _track_active_speaker(self) -> None:
        """Watch Active Speaker Button(50000) [l=1506,t=1174,r=1548,b=1190] continuously.

        - Identifies who is on the microphone and updates `self._current_speaker` even if OCR resolves the real
          username 1 second after the button first appears (`Speaker_On_Mic[...]` -> `ActualUsername`).
        - Connects live audio transcription strictly to the active speaker at [1506,1174,1548,1190].
        - Detects when the speaker's name disappears to record total mic grab duration + full transcript.
        """
        speaker = None
        if hasattr(self.ui_automation, "get_active_speaker"):
            speaker = self.ui_automation.get_active_speaker()
        now_mono = time.monotonic()

        # If the speaker button is still held by the same person, but OCR just resolved "Speaker_On_Mic[...]" into the real username,
        # upgrade self._current_speaker in-place without ending the current mic grab!
        if (
            speaker
            and self._current_speaker
            and self._current_speaker.startswith("Speaker_On_Mic")
            and not speaker.startswith("Speaker_On_Mic")
        ):
            self._current_speaker = speaker
            self._emit_bot_log(f"[INCOMING MIC 🎙️] Active Speaker OCR resolved -> '{speaker}' on microphone at {ACTIVE_SPEAKER_RECT}")

        if speaker != self._current_speaker:
            if (
                self._current_speaker
                and self._speaker_started_mono > 0
                and self._current_speaker.casefold() != BOT_USERNAME.casefold()
            ):
                duration = max(0.5, now_mono - self._speaker_started_mono)
                full_transcript = " ".join(self._current_speaker_chunks).strip()
                self.store.record_mic_grab(
                    self._current_speaker,
                    self._speaker_started_iso,
                    duration,
                    transcript=full_transcript,
                )
                self._emit_bot_log(
                    f"[INCOMING MIC 🎙️] {self._current_speaker} released mic ({duration:.1f}s)"
                    + (f" | Full Mic Transcript: \"{full_transcript}\"" if full_transcript else "")
                )
            self._current_speaker = speaker
            self._speaker_started_iso = now_iso() if speaker else ""
            self._speaker_started_mono = now_mono if speaker else 0.0
            self._current_speaker_chunks = []
            if speaker:
                # Detect gender color on the active speaker banner if available
                gender_tag = ""
                if hasattr(self.ui_automation, "detect_user_gender_from_rect") and not speaker.startswith("Speaker_On_Mic"):
                    g_color = self.ui_automation.detect_user_gender_from_rect(ACTIVE_SPEAKER_RECT)
                    if g_color in {"male", "female"}:
                        gender_str = f"{g_color} ({'blue' if g_color == 'male' else 'pink'})"
                        self.store.update_user_attributes(speaker, gender=gender_str)
                        gender_tag = f" [{gender_str}]"
                self._emit_bot_log(
                    f"[INCOMING MIC 🎙️] SPEAKER_ON_MIC: '{speaker}'{gender_tag} grabbed mic at {ACTIVE_SPEAKER_RECT} -> Live terminal transcription active!"
                )
                # Immediately kick off the first live audio transcription slice as soon as they grab the mic!
                if (
                    speaker.casefold() != BOT_USERNAME.casefold()
                    and self.settings.get("transcription_mode", True)
                    and not self.dry_run
                ):
                    self._spawn_speaker_transcribe_worker(speaker)

        # While a real room user is speaking on the mic and transcription_mode is enabled, continuously transcribe audio chunks
        if (
            speaker
            and speaker.casefold() != BOT_USERNAME.casefold()
            and self.settings.get("transcription_mode", True)
            and not self.dry_run
            and (now_mono - self._last_transcribe_mono) >= 2.9
        ):
            self._spawn_speaker_transcribe_worker(speaker)

        # When Active Speaker [1506,1174,1548,1190] clears (nobody on mic), flush queued TTS broadcasts
        if (
            speaker is None
            and self._queued_broadcasts
            and not self.settings.get("silent_mode", False)
            and hasattr(self.ui_automation, "broadcast_tts_via_vbcable")
        ):
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
                self._emit_bot_log(f"[INCOMING PRESENCE] {event['action'].upper()}: {event['user']}")
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
            self._emit_bot_log(
                f"[INCOMING MODERATION] {moderation['actor']} {moderation['action']} {moderation['target']}"
            )
            return

        # Ignore our own outbound messages when dispatching chat triggers so KaeKae never loops on herself
        if sender.casefold() == BOT_USERNAME.casefold():
            return

        for reply in self._dispatch(sender, text):
            self.send_reply(sender, reply)

    def _generate_kaekae_contextual_reply(self, sender: str, text: str) -> str:
        """Trigger 1: (kaekae or Kaekae) — High-speed compartmentalized contextual intelligence engine:
        Compartmentalizes memory across:
        1. User Identity & Demographic Compartment (gender, title, room duration, message count)
        2. Psychometric & Sentiment Compartment (text tone, audio tone, speech cadence/patterns)
        3. Lexical Compartment (favorite nouns, frequent topics, pet phrases)
        4. Audio/Microphone Compartment (mic grab count, duration, recent speech transcripts)
        5. Live Room Atmosphere Compartment (active speaker on mic, last 10 messages, hot topics)
        Synthesizes an immediate, razor-sharp, witty response tailored specifically to the user's personality!
        """
        last_10 = list(self._recent_messages)[-10:]
        profile = self.store.user_profile(sender)
        cleaned_prompt = re.sub(r"\bkaekae(?:_toad)?\b[\s,:!\-]*", "", text, flags=re.IGNORECASE).strip()

        # Compartment 1: Demographic & Identity
        user_gender = str(profile.get("gender", "unknown")) if profile else "unknown"
        user_msgs = int(profile.get("message_count", 1)) if profile else 1
        chat_mins = float(profile.get("chat_duration_seconds", 0.0)) / 60.0 if profile else 0.0

        # Compartment 2: Psychometrics & Tone
        user_tone = str(profile.get("text_tone", "chill")) if profile else "chill"
        audio_tone = str(profile.get("audio_tone", "neutral")) if profile else "neutral"
        speech_style = str(profile.get("speech_patterns", "conversational")) if profile else "conversational"

        # Compartment 3: Lexical Topics & Favorite Nouns
        user_noun = str(profile.get("top_noun", "n/a")) if profile else "n/a"

        # Compartment 4: Audio & Mic Memory
        mic_grabs = int(profile.get("mic_grab_count", 0)) if profile else 0
        mic_transcripts = profile.get("mic_transcripts", []) if profile else []
        last_mic_said = f'"{mic_transcripts[0][:50]}"' if mic_transcripts else ""

        # Compartment 5: Room Atmosphere
        active_mic = self._current_speaker or "None (Mic Free)"
        recent_topics: list[str] = []
        recent_speakers: list[str] = []
        for spk, line in reversed(last_10):
            if spk.casefold() != BOT_USERNAME.casefold():
                if spk not in recent_speakers:
                    recent_speakers.append(spk)
                noun, _ = extract_top_noun([line])
                if noun != "n/a" and noun not in recent_topics:
                    recent_topics.append(noun)

        context_snippet = last_10[-2][1] if len(last_10) >= 2 else (last_10[-1][1] if last_10 else text)
        low_q = (cleaned_prompt or text).lower()
        is_question = "?" in text or bool(
            re.match(r"^(what|who|where|when|why|how|are|is|do|does|can|will|should|did|tell|gimme|give)\b", low_q)
        )

        if is_question:
            if any(k in low_q for k in ("how are you", "how you doing", "whats up", "what's up", "wyd")):
                base = (
                    f"@{sender}, I'm locked in watching {len(recent_speakers) or 1} active chatters (active mic: {active_mic}). "
                    f"You've dropped {user_msgs} messages in {chat_mins:.0f}m with that signature {user_tone} style!"
                )
            elif any(k in low_q for k in ("who is on mic", "who's on mic", "who is talking", "speaker")):
                base = f"@{sender}, radar sweep on [1506,1174,1548,1190]: Active Speaker is {active_mic}!"
            elif any(k in low_q for k in ("who am i", "my info", "what do you know about me")):
                mic_part = f", plus {mic_grabs} mic grabs" if mic_grabs else ""
                base = (
                    f"@{sender}, my compartmentalized memory has you pegged: {user_gender}, {user_msgs} chat lines{mic_part}, "
                    f"favorite noun '{user_noun}', {speech_style} cadence, and a distinctly {user_tone} energy!"
                )
            elif any(k in low_q for k in ("roast me", "diss me")):
                base = f"@{sender}, " + self._pick_unique_diss(sender)
            else:
                topic_str = f"'{recent_topics[0]}'" if recent_topics else f"'{user_noun}'"
                witty_spices = (
                    f"With your {user_tone} take on {topic_str}, my tactical answer is: bet on the numbers, watch the cooldown clock, and stay ahead of the curve.",
                    f"Cross-referencing your {user_msgs} messages and '{user_noun}' focus: the answer is a firm YES, but keep 5,000 PAT ready.",
                    f"Looking at how the lounge is moving right now: '{context_snippet[:60]}' was the preamble, but your question cuts straight to the core.",
                )
                chosen_spice = witty_spices[hash(sender + text) % len(witty_spices)]
                base = f"@{sender}, {chosen_spice} (Caught: {(cleaned_prompt or text)[:75]})"
        else:
            # Contextual witty conversational comeback
            mic_tease = f" (still remember when you said {last_mic_said} on mic)" if last_mic_said else ""
            witty_comebacks = (
                f"@{sender}, heard loud and clear! Tracking your {user_msgs} lines and that {user_tone} vibe{mic_tease}: '{(cleaned_prompt or text)[:90]}'",
                f"@{sender}, you always bring that {speech_style} energy to '{user_noun}'—I'm all ears on: '{(cleaned_prompt or text)[:90]}'",
                f"@{sender}, logged straight into my neural memory banks! Context says we're rolling with it.",
            )
            base = witty_comebacks[hash(sender + text) % len(witty_comebacks)]

        return self._apply_tone(base)

    def _generate_idk_reply(self, sender: str, question: str) -> str:
        """Trigger 15: !idk <question> — Instant smart answer or witty contextual comeback."""
        q = question.strip()
        if not q:
            return self._apply_tone(f"@{sender}, give me a question after !idk and I'll drop the knowledge.")
        low = q.lower()
        profile = self.store.user_profile(sender)
        fav_noun = str(profile.get("top_noun", "chat")) if profile else "chat"

        # Smart math evaluator if the question contains an arithmetic expression
        math_m = re.search(r"(\d+(?:\.\d+)?)\s*([+\-*/])\s*(\d+(?:\.\d+)?)", low)
        if math_m:
            a, op, b = float(math_m.group(1)), math_m.group(2), float(math_m.group(3))
            res = a + b if op == "+" else (a - b if op == "-" else (a * b if op == "*" else (a / b if b != 0 else 0.0)))
            return self._apply_tone(f"@{sender}, quick math says {res:g}—faster than a 20.2s wheel spin.")

        if "jackpot" in low or "spin" in low or "pat" in low:
            ans = f"@{sender}, every !spin costs 5,000 PAT with a 20s cooldown, feeds the 5,000,000 PAT Golden Jackpot, and triggers Pity Surge after 6 losses!"
        elif "heist" in low or "bail" in low or "vault" in low:
            ans = f"@{sender}, INT 18 + DEX 16 + CON 15 is the strongest Mastermind build—and !bail before the vault door saves your loot +20%!"
        elif low.startswith(("why ", "how come")):
            ans = f"@{sender}, because in Players__Lounge chaos is a feature, not a bug (and your top noun '{fav_noun}' proves it) regarding: {q[:120]}"
        elif low.startswith(("when ", "what time")):
            ans = f"@{sender}, right after the next wheel cooldown—or whenever '{fav_noun}' stops trending in chat: {q[:120]}"
        elif low.startswith(("who ", "whose")):
            spk = self._current_speaker or sender
            ans = f"@{sender}, all signs in my SQLite database point straight to {spk} on: {q[:120]}"
        else:
            witty_pool = (
                f"@{sender}, smart money says: trust the math, keep 5,000 PAT in reserve, and never bet against KaeKae_Toad on '{q[:110]}'.",
                f"@{sender}, I cross-checked the last {len(self._recent_messages)} lines and your '{fav_noun}' habit—the verdict on '{q[:110]}' is 100% certified facts.",
                f"@{sender}, even the Crowned Gambling Frog in the sky knows the answer to '{q[:110]}' is to play it cool and collect the payout.",
            )
            ans = witty_pool[hash(q) % len(witty_pool)]
        return self._apply_tone(ans)

    def _pick_unique_diss(self, target: str) -> str:
        """Pick a never-before-used diss from _UNIQUE_DISS_TEMPLATES so !diss NEVER repeats a roast."""
        available = [t for t in _UNIQUE_DISS_TEMPLATES if t not in self._used_disses]
        if not available:
            # If all 40 templates have been exhausted, synthesize a fresh dynamic profile-based diss
            profile = self.store.user_profile(target)
            noun = str(profile.get("top_noun", "keyboard")) if profile else "keyboard"
            msgs = int(profile.get("message_count", 0)) if profile else len(self._used_disses)
            dynamic = (
                f"{target}, Roast #{len(self._used_disses) + 1}: after {msgs} messages and obsessing over '{noun}', "
                f"your banter still couldn't pass a Round 1 store heist check."
            )
            self._used_disses.add(dynamic)
            return self._apply_tone(dynamic)
        chosen_tpl = random.choice(available)
        self._used_disses.add(chosen_tpl)
        return self._apply_tone(chosen_tpl.format(target=target))

    def _dispatch(self, sender: str, text: str) -> list[str]:
        raw = text.strip()
        normalized = raw.casefold()

        # Trigger 14: (-) single line of text prompts the bot to send the next page of information
        if raw == "-":
            return self._next_page(sender)

        # Trigger 16: Moderation History Queries (who kicked/blocked/unblocked/banned/unbanned/punished/unpunished <username>)
        history = _HISTORY_RE.match(raw)
        if history:
            return self._history_reply(sender, history.group("action").lower(), history.group("target"))

        # Trigger 2: !chat — Turn Chat Mode ON (mingles and comments on room text and the users sending them)
        if normalized == "!chat":
            self.settings["chat_mode"] = True
            self.settings["silent_mode"] = False
            self._self_notice("Chat mode is ON — KaeKae_Toad is mingling and watching the room.")
            return []

        # Trigger 3: !chatoff — Turn Chat Mode OFF
        if normalized in {"!chatoff", "!chat off"}:
            self.settings["chat_mode"] = False
            self._diss_jobs.clear()
            self._self_notice("Chat mode is off.")
            return []

        # Trigger 4: !shutup — Turns off all replies, broadcasts, and any other form of audio or text communication
        if normalized == "!shutup":
            self.silent_switch(True)
            self._self_notice("Silent mode engaged — all room replies, broadcasts and audio suppressed.")
            return []

        # Trigger 5: !transcribe — Turn live room speech transcription ON (posts [MIC] <Speaker>: <Text> in real time)
        if normalized == "!transcribe":
            self.settings["transcription_mode"] = True
            self.settings["post_transcripts_to_chat"] = True
            cur_spk = self._current_speaker or "none (waiting for speaker)"
            self._self_notice(
                f"Transcription mode is ON (posting [MIC] <Speaker>: <Text> in real time; current speaker: {cur_spk})."
            )
            return []

        # Trigger 6: !transcribed — Turn off live room speech transcriptions
        if normalized == "!transcribed":
            self.settings["transcription_mode"] = False
            self.settings["post_transcripts_to_chat"] = False
            if self._recent_transcripts:
                last_ts, last_spk, last_txt = self._recent_transcripts[-1]
                self._self_notice(f"Transcription is OFF. Last transcribed [MIC] {last_spk}: {last_txt}")
            else:
                self._self_notice("Transcription is off.")
            return []

        # Trigger 7: !suppress — Opts user out and dumps data into separate folder (`data/suppressed_users`)
        if normalized == "!suppress":
            self._self_notice(
                "Stored profile and history were dumped to the separate vault folder and removed from bot queries."
                if self.store.suppress(sender)
                else "Profile is already suppressed."
            )
            return []

        # Trigger 8: !unsuppress — Restores dumped data from separate folder back into active database
        if normalized == "!unsuppress":
            self._self_notice(
                "Stored profile and history were restored from the vault."
                if self.store.unsuppress(sender)
                else "No recoverable suppressed profile was found."
            )
            return []

        # Trigger 11: !who is <username> — Generates a narrative biography of the user from chat & mic history
        if normalized.startswith("!who is "):
            return self._who_is(raw[8:].strip())

        # Trigger 12: !info on <username> — Statistical profile: audio & text tone, top NOUN, message count, 24h mic grabs
        if normalized.startswith("!info on "):
            return self._info_on(raw[9:].strip())

        # Trigger 13: !grabs [username] [duration] — 5m up to 72h flexible increments
        if normalized.startswith("!grabs"):
            return self._grabs(raw[6:].strip())

        # Trigger 15: !idk <question> — Instant smart answer or witty contextual comeback
        if normalized.startswith("!idk"):
            question = raw[4:].strip()
            return [self._generate_idk_reply(sender, question)]

        # Voice listing & switching (!voices / !voice <name>) — operator-only status, NEVER posted to room
        if normalized in {"!voices", "!voice"}:
            voice_list = ", ".join(f"{alias} ({voice})" for alias, voice in EDGE_TTS_VOICES.items())
            coqui_list = ", ".join(sorted(set(list(COQUI_FEMALE_VOICES.values()) + [COQUI_DEFAULT_VOICE])))
            current_voice = getattr(self.ui_automation, "tts_voice", self.settings.get("tts_voice", EDGE_TTS_DEFAULT_VOICE))
            self._self_notice(
                f"Current Neural Voice: {current_voice}. Switch with !voice <name>. "
                f"Coqui Female Voices: {coqui_list}. Edge Female Voices: {voice_list}"
            )
            return []
        if normalized.startswith("!voice "):
            requested = raw[7:].strip()
            if hasattr(self.ui_automation, "set_tts_voice"):
                chosen = self.ui_automation.set_tts_voice(requested)
            else:
                chosen = EDGE_TTS_VOICES.get(requested.casefold(), requested or EDGE_TTS_DEFAULT_VOICE)
            self.settings["tts_voice"] = chosen
            self._self_notice(f"Neural TTS voice set to: {chosen}. Try !say \"hello room\"")
            return []

        # Trigger 9: !say "message" — Grabs Camfrog Talk button by clicking & holding to broadcast, then releases click
        if normalized.startswith("!say"):
            phrase = raw[4:].strip().strip('"').strip("'")
            if not phrase:
                self._self_notice('Usage: !say "message"')
                return []
            if self.settings.get("silent_mode"):
                return []
            active_speaker = (
                self.ui_automation.get_active_speaker()
                if hasattr(self.ui_automation, "get_active_speaker")
                else None
            )
            if active_speaker and active_speaker.casefold() != BOT_USERNAME.casefold():
                self._queued_broadcasts.append(phrase)
                self._self_notice(
                    f"Mic in use by {active_speaker}; queued broadcast until mic clears: {phrase[:140]}"
                )
                return []
            if hasattr(self.ui_automation, "broadcast_tts_via_vbcable"):
                ok = self.ui_automation.broadcast_tts_via_vbcable(phrase, dry_run=self.dry_run)
                if ok:
                    voice_used = getattr(self.ui_automation, "tts_voice", EDGE_TTS_DEFAULT_VOICE)
                    self._self_notice(
                        f"Broadcasted via VB-Cable [{voice_used}] (grabbed Talk {TALK_BUTTON_RECT}, released mic cleanly): {phrase[:120]}"
                    )
                else:
                    self._self_notice(f"VB-Cable TTS failed: {self.ui_automation.last_error}")
                return []
            self._self_notice("VB-Cable TTS adapter unavailable.")
            return []

        # Trigger 10: !diss <username> (or !diss for the whole room) — Roasts target immediately + continuous 1-min unique roasts
        if normalized.startswith("!diss"):
            arg_target = raw[5:].strip()
            target = clean_username(arg_target) if arg_target and arg_target.lower() not in {"the room", "room", "all"} else "the room"
            self.settings["chat_mode"] = True
            first_roast = self._pick_unique_diss(target)
            self._diss_jobs[target] = time.monotonic() + 60.0
            # The roast itself is real chat (the action), but the meta-status about continuous mode is operator-only.
            return [first_roast]

        # Triggers 17, 18, 19: !happy, !sad, !mad — Gives the bot happy/sad/angry tone in all that it does (only when !chat is ON)
        if normalized in {"!happy", "!sad", "!mad"}:
            if not self.settings["chat_mode"]:
                self._self_notice("Turn on chat mode first with !chat.")
                return []
            self.settings["tone"] = normalized[1:]
            self._self_notice(f"Tone set to {normalized[1:]}.")
            return []

        # Trigger 20: !triggers — Gives a list of all triggers and options (operator-only, NEVER posted to room)
        if normalized in {"!triggers", "!help"}:
            self._self_notice(
                "KaeKae_Toad Triggers: (1) kaekae <question/statement>, (2) !chat, (3) !chatoff, (4) !shutup, "
                "(5) !transcribe, (6) !transcribed, (7) !suppress, (8) !unsuppress, (9) !say \"message\", "
                "(10) !diss [user], (11) !who is <user>, (12) !info on <user>, (13) !grabs [user] [5m..72h], "
                "(14) - (next page), (15) !idk <question>, (16) who kicked/blocked/unblocked/banned/unbanned/punished/unpunished <user>, "
                "(17) !happy, (18) !sad, (19) !mad, (20) !triggers."
            )
            return []

        if normalized in {"!admins", "!admin"}:
            admin_list = ", ".join(sorted(MODERATION_ALLOWED_SENDERS)) or "none"
            self._self_notice(f"Authorized KaeKae_Toad Administrators: {admin_list}. Add with: !admin add <username>")
            return []
        if normalized.startswith("!admin add "):
            if sender.casefold() not in {name.casefold() for name in MODERATION_ALLOWED_SENDERS}:
                self._self_notice(f"@{sender}, only an existing administrator can add a new administrator.")
                return []
            new_admin = clean_username(raw[11:].strip())
            if not new_admin:
                self._self_notice("Usage: !admin add <username>")
                return []
            MODERATION_ALLOWED_SENDERS.add(new_admin)
            try:
                from config import save_calibration_overrides
                save_calibration_overrides({"allowed_admins": sorted(MODERATION_ALLOWED_SENDERS)})
            except Exception:
                pass
            self._self_notice(f"Added '{new_admin}' to KaeKae_Toad administrators!")
            return []

        native = re.match(r"^!(unpunish|unblockmic|unban|topic|watchlist|kick|ban|punish|blockmic)\s+(.+)$", raw, re.I)
        if native:
            return self._native_moderation(sender, native.group(1).lower(), native.group(2).strip())

        # Trigger 1: (kaekae or Kaekae) — Not case sensitive, does NOT require '!'
        if re.search(r"\bkaekae\b", normalized, re.I):
            if self.settings.get("silent_mode"):
                return []
            return [self._generate_kaekae_contextual_reply(sender, raw)]

        # Trigger 2 active mingling: when !chat is ON, mingle and comment on room text & users if addressed or periodically
        if (
            self.settings.get("chat_mode")
            and not self.settings.get("silent_mode")
            and not raw.startswith("!")
            and len(raw) >= 12
        ):
            now_m = time.monotonic()
            if (now_m - self._last_mingle_mono) >= 45.0 and ("?" in raw or len(self._recent_messages) >= 4):
                self._last_mingle_mono = now_m
                profile = self.store.user_profile(sender)
                noun = str(profile.get("top_noun", "chat")) if profile else "chat"
                mingle_line = self._apply_tone(
                    f"@{sender}, real talk on '{raw[:70]}'—matches your '{noun}' vibe in here!"
                )
                return [mingle_line]

        return []

    def _native_moderation(self, sender: str, action: str, argument: str) -> list[str]:
        if action not in NATIVE_MODERATION_COMMANDS:
            return []
        if sender.casefold() not in {name.casefold() for name in MODERATION_ALLOWED_SENDERS}:
            return ["Native moderation commands are disabled until an operator is added to MODERATION_ALLOWED_SENDERS."]
        return [f"/{action} {argument}".strip()]

    def _who_is(self, username: str) -> list[str]:
        """Trigger 11: !who is <username> — Narrative biography from chat & microphone history."""
        username = clean_username(username)
        profile = self.store.user_profile(username)
        if not profile:
            return [f"No stored profile for {username or 'that user'}."]
        samples = profile["messages"][:3]
        sample_text = " | ".join(samples) if samples else "no saved chat yet"
        mic_tx = profile.get("mic_transcripts") or []
        mic_snippet = f" | Recent Mic: \"{mic_tx[0][:60]}\"" if mic_tx else ""
        chat_mins = float(profile.get("chat_duration_seconds") or 0.0) / 60.0
        status = "in room" if profile.get("active") else "left room"
        gender = profile.get("gender", "unknown")
        style = profile.get("speech_patterns", "conversational")
        grabs, mic_sec = self.store.mic_stats(str(profile["username"]), 72 * 3600)
        reply = (
            f"Biography of {profile['username']} [{gender}, {status}, {chat_mins:.1f}m in room]: "
            f"Seen since {profile['first_seen']} with {profile['message_count']} messages ({style} style, "
            f"top noun '{profile.get('top_noun', 'n/a')}', {grabs} mic grabs / {mic_sec:.0f}s). "
            f"Recent chat: {sample_text}{mic_snippet}"
        )
        return [self._apply_tone(reply)]

    def _info_on(self, username: str) -> list[str]:
        """Trigger 12: !info on <username> — Statistical profile: audio & text tone, top NOUN used, message count, and 24h mic grabs."""
        username = clean_username(username)
        profile = self.store.user_profile(username)
        if not profile:
            return [f"No stored statistics for {username or 'that user'}."]
        grabs, seconds = self.store.mic_stats(str(profile["username"]), 24 * 3600)
        chat_mins = float(profile.get("chat_duration_seconds") or 0.0) / 60.0
        reply = (
            f"{profile['username']}: {profile['message_count']} messages; "
            f"text tone: {profile.get('text_tone', 'neutral')}; audio tone: {profile.get('audio_tone', 'neutral')}; "
            f"top noun '{profile.get('top_noun', profile['top_word'])}' (top word '{profile['top_word']}' {profile['top_count']}x); "
            f"room time {chat_mins:.1f}m; {grabs} mic grabs / {seconds:.0f}s in 24h."
        )
        return [self._apply_tone(reply)]

    @staticmethod
    def _parse_flexible_duration_seconds(token: str) -> int | None:
        """Parse flexible increments from 5 minutes up to 72 hours (e.g. 5m, 15m, 30m, 45m, 1h, 6h, 12h, 24h, 48h, 72h, 2d, 3d)."""
        m = re.fullmatch(r"(\d+)\s*(m|min|mins|h|hr|hrs|d|day|days)", token.strip(), re.I)
        if not m:
            return None
        val = int(m.group(1))
        unit = m.group(2).lower()[0]
        sec = val * 60 if unit == "m" else (val * 3600 if unit == "h" else val * 86400)
        # Clamp strictly between 5 minutes (300s) and 72 hours (259,200s)
        return max(300, min(72 * 3600, sec))

    def _grabs(self, arguments: str) -> list[str]:
        """Trigger 13: !grabs [username] [duration] — Shows microphone grab counts and total speaking time
        in flexible increments from 5 minutes up to 72 hours.
        """
        parts = arguments.split()
        username = None
        seconds = 86400  # default 24h
        duration_label = "1440 minutes (24h)"
        for part in parts:
            parsed_sec = self._parse_flexible_duration_seconds(part)
            if parsed_sec is not None:
                seconds = parsed_sec
                if seconds % 3600 == 0 and seconds >= 3600:
                    duration_label = f"{seconds // 60} minutes ({seconds // 3600}h)"
                else:
                    duration_label = f"{seconds // 60} minutes"
            else:
                username = clean_username(part) or username
        count, duration = self.store.mic_stats(username, seconds)
        label = username or "room"
        return [self._apply_tone(f"Mic grabs for {label}: {count} grabs, {duration:.0f}s over the last {duration_label}.")]

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
        for target, due in list(self._diss_jobs.items()):
            if now >= due:
                roast_line = self._pick_unique_diss(target)
                self.send_reply(target, roast_line)
                self._diss_jobs[target] = now + 60.0

    def send_reply(self, recipient: str, message: str) -> bool:
        if self.settings["silent_mode"]:
            LOG.info("Silent mode suppressed reply to %s: %s", recipient, message)
            return False
        sent = True
        for page in self._split_for_chat(message):
            if self.dry_run:
                LOG.info("DRY RUN reply to %s: %s", recipient, page)
                self._emit_bot_log(f"[KAEKAE REPLY -> {recipient}] {page}")
            else:
                sent = self.ui_automation.send_chat_message(page) and sent
                if sent:
                    self._emit_bot_log(f"[KAEKAE REPLY -> {recipient}] {page}")
                else:
                    LOG.error("%s", self.ui_automation.last_error)
                    break
        return sent

    @staticmethod
    def _split_for_chat(message: str) -> list[str]:
        text = str(message).strip()
        return [text[index:index + MAX_CHAT_MESSAGE_LENGTH] for index in range(0, len(text), MAX_CHAT_MESSAGE_LENGTH)] or [""]

    def run(self, interval: float = POLL_INTERVAL_SECONDS) -> None:
        if not self.running and not self.initialize():
            raise RuntimeError(self.ui_automation.last_error or "Unable to connect to Camfrog")
        while self.running:
            self.poll_once()
            time.sleep(interval)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Camfrog UI Automation bot (with VB-Cable TTS & Active Speaker Gate)")
    parser.add_argument("--dry-run", action="store_true", help="Do not send messages into Camfrog")
    parser.add_argument("--once", action="store_true", help="Run one UIA polling cycle and exit")
    parser.add_argument("--interval", type=float, default=POLL_INTERVAL_SECONDS, help="Polling interval in seconds")
    parser.add_argument("--silent", action="store_true", help="Start with silent mode enabled")
    parser.add_argument("--print-layout", action="store_true", help="Print detected Camfrog UIA coordinates and exit")
    return parser


def main(argv: list[str] | None = None) -> int:
    try:
        from setup_env import bootstrap_environment
        bootstrap_environment()
    except Exception:
        pass
    args = build_parser().parse_args(argv)
    bot = CamfrogBot(dry_run=args.dry_run)
    if args.silent:
        bot.silent_switch(True)
    if args.print_layout:
        if not bot.ui_automation.connect_to_camfrog():
            print(bot.ui_automation.last_error)
            return 1
        print(json.dumps(bot.ui_automation.layout_locations(), indent=2))
        return 0
    if args.once:
        if not bot.initialize(mark_existing_seen=False):
            print(bot.ui_automation.last_error)
            return 1
        bot.poll_once()
        return 0
    bot.run(interval=args.interval)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
