from pywinauto import Application
import requests
import pyautogui
import pyperclip
import re
import time
import json
import os
import random
import asyncio
import threading
import traceback
import wave
from difflib import SequenceMatcher
import keyboard
import edge_tts
import pygame
import pytesseract
import speech_recognition as sr

try:
    import sounddevice as sd
    import numpy as np
except ImportError:
    sd = None
    np = None

try:
    from faster_whisper import WhisperModel
except ImportError:
    WhisperModel = None

from datetime import datetime, timedelta


shutdown_event = threading.Event()


BOT_TRIGGERS = ["!kk", "!KaeKae", "KaeKae", "kae", "kaebot"]
BOT_USERNAME = "KaeKae"
AUTHORIZED_USERS = {"dog3lived", "b3_dee", "b3_d33", "dog", "$htickie"}
AUTHORIZED_TITLES = ("Pop", "Father", "Creator")
IGNORED_USERS = {"players_lounge1", "drama1", "apubot", "kimmy_cakes"}
AGGRESSIVE_PHRASES = ("not a pepe", "not like pepe", "dogshit bot")
AGGRESSIVE_INSULTS = (
    "dumb",
    "stupid",
    "worthless",
    "temu",
    "idiot",
    "useless",
    "trash",
    "garbage",
    " moron",
)
BOT_TONE = "normal"
RESPONSES_MUTED = False

PERSONALITY = """
You are KaeKae.

Your personality:
- witty
- carefree
- funny
- confident
- playful
- chill
- clever
- sarcastic
- female
- feminine, bubbly, and preppy
- playful valley-girl energy

Rules:
- Heavy teasing is okay.
- Keep answers short.
- Usually respond in 1-2 sentences.
- Be entertaining.
- Use a playful, confident, preppy valley-girl style when appropriate.
- Casual phrases like "literally," "like," "totally," and "honestly" are okay.
- Sound fashionable, carefree, teasing, and socially confident.
- Keep the persona fun and adult without becoming explicit.
- Act like the coolest person in the room.
- NEVER repeat an answer you've already given. If the same question comes up again, give a completely different response.
- If someone was recently kicked, blocked, punished, banned or any other action was taken, you can tease the person who did it or mock the victim. Reference the time it happened.
- If you know a user from your memory, reference them by name and personalize your response.
- ALWAYS address the user by their username when responding to them.
"""

# --- Settings ---
AMBIENT_CHANCE = 0.03
PEPEFROG_STATEMENT = "PepeFrog Pshh just a bunch of 1's and 0's incorrectly placed."
PEPEFROG_STATEMENT_CHANCE = 0.25
REACT_WORDS = ["idiot", "noob", "dog", "bryan"]
VOICE = "en-US-JennyNeural"
VOICE_RATE = "-5%"
VOICE_PITCH = "+0Hz"
KICK_FILE = "bot_kicks.json"
USERS_FILE = "bot_users.json"
USER_MESSAGES_FILE = "user_messages.jsonl"
AUDIO_TRANSCRIPTS_FILE = "audio_transcripts.jsonl"
MAX_PROFILE_ITEMS = 999
MAX_USER_CONTEXT_CHARS = 12000
OCR_INTERVAL = 12
OCR_PAUSE_AFTER_QUERY = 30
VOICE_TRIGGERS = ["kaekae", "kk"]
VOICE_COOLDOWN = 5
REPEAT_COOLDOWN = 3
VOICE_ENABLED = False
LISTENING_ENABLED = True
TRANSCRIBE_ENABLED = False
AUDIO_INPUT_DEVICE = "CABLE Output (VB-Audio Virtual Cable)"
AUDIO_OUTPUT_DEVICE = "Speakers (Razer USB Sound Card)"
AUDIO_CLIPS_DIR = "audio_clips"
WHISPER_MODEL_SIZE = "base.en"
LOG_WINDOW_HOURS = 72
MAX_MSG_LENGTH = 440

# --- Repeat Mode State ---
repeat_mode = False
_last_repeat_time = 0
_last_ocr_pause = 0
recent_bot_messages = {}
BOT_MESSAGE_DEDUP_SECONDS = 120
pending_verbatim = None

# --- User Tracking ---
def build_short_biography(username, profile):
    nickname = profile.get("nickname", username)
    topics = profile.get("topics", [])
    message_count = profile.get("message_count", 0)
    corrections = profile.get("corrections", [])

    if corrections:
        summary = corrections[-1].split("] ", 1)[-1]
    elif topics:
        topic_text = ", ".join(topics[-5:])
        summary = f"{nickname} has shared {message_count} messages, often discussing {topic_text}."
    else:
        summary = f"{nickname} has shared {message_count} messages in the chatroom."

    summary = " ".join(summary.split()).strip()
    if len(summary) > 300:
        summary = summary[:297].rstrip(" ,.;:") + "..."
    if len(summary) < 15:
        summary = f"Chatroom user {nickname}."
    return summary

def load_users():
    if os.path.exists(USERS_FILE):
        with open(USERS_FILE, "r") as f:
            users = json.load(f)
        changed = False
        for username, profile in users.items():
            if not profile.get("biography"):
                profile["biography"] = build_short_biography(username, profile)
                changed = True
        if changed:
            save_users(users)
        return users
    return {}

def save_users(users):
    with open(USERS_FILE, "w") as f:
        json.dump(users, f)

def record_chat_message(users, username, message, timestamp, source, archived_messages):
    message_key = f"{username.lower().strip()}|{timestamp}|{message.strip()}"
    if message_key in archived_messages:
        return

    archived_messages.add(message_key)
    update_user(users, username, message, timestamp)
    save_users(users)
    with open(USER_MESSAGES_FILE, "a", encoding="utf-8") as f:
        json.dump({
            "username": username,
            "timestamp": timestamp,
            "message": message,
            "source": source,
        }, f)
        f.write("\n")

def load_archived_message_keys():
    archived_messages = set()
    if not os.path.exists(USER_MESSAGES_FILE):
        return archived_messages

    with open(USER_MESSAGES_FILE, "r", encoding="utf-8") as f:
        for line in f:
            try:
                entry = json.loads(line)
                archived_messages.add(
                    f"{entry['username'].lower().strip()}|{entry['timestamp']}|{entry['message'].strip()}"
                )
            except (KeyError, json.JSONDecodeError):
                continue
    return archived_messages

def update_user(users, username, message, timestamp):
    if username.lower() == BOT_USERNAME.lower():
        return
    user_key = next((key for key in users if key.lower() == username.lower()), username)
    if user_key not in users:
        users[user_key] = {
            "nickname": username,
            "first_seen": datetime.now().strftime("%Y-%m-%d %I:%M %p"),
            "last_seen": datetime.now().strftime("%Y-%m-%d %I:%M %p"),
            "message_count": 0,
            "topics": [],
            "quotes": [],
            "corrections": [],
            "biography": "",
            "microphone_transcripts": []
        }
    profile = users[user_key]
    profile.setdefault("nickname", user_key)
    profile.setdefault("topics", [])
    profile.setdefault("quotes", [])
    profile.setdefault("corrections", [])
    profile.setdefault("biography", "")
    profile.setdefault("microphone_transcripts", [])
    profile.setdefault("message_count", 0)
    profile["last_seen"] = timestamp
    profile["message_count"] += 1

    topic_words = ["game", "stream", "music", "movie", "food", "car", "job", "work",
                   "school", "family", "friend", "party", "lol", "haha", "damn",
                   "bro", "dude", "ngl", "fr", "tbh", "irl", "vibe", "chill"]
    msg_lower = message.lower()
    nickname_match = re.search(
        r"\b(?:my nickname is|call me|my name is)\s+([\w$-]{2,40})",
        message,
        flags=re.IGNORECASE,
    )
    if nickname_match:
        profile["nickname"] = nickname_match.group(1)
    for t in topic_words:
        if t in msg_lower and t not in profile["topics"]:
            profile["topics"].append(t)
            if len(profile["topics"]) > MAX_PROFILE_ITEMS:
                profile["topics"].pop(0)

    if len(message) > 20 and len(message) < 150:
        profile["quotes"].append(f"[{timestamp}] {message}")
        if len(profile["quotes"]) > MAX_PROFILE_ITEMS:
            profile["quotes"].pop(0)

    profile["biography"] = build_short_biography(user_key, profile)

def build_user_context(users, username):
    user_key = next((key for key in users if key.lower() == username.lower()), None)
    if user_key is None:
        return ""
    u = users[user_key]
    topics = ", ".join(u.get("topics", [])) if u.get("topics") else "none yet"
    quotes = u.get("quotes", [])
    quote_str = "\n".join(f"    \"{q}\"" for q in quotes)
    microphone_text = "\n".join(
        f"    [{item.get('timestamp', 'unknown')}] "
        f"({item.get('tone', 'unknown')}) {item.get('message', '')}"
        for item in u.get("microphone_transcripts", [])
    ) or "none recorded"

    history_lines = []
    if os.path.exists(USER_MESSAGES_FILE):
        with open(USER_MESSAGES_FILE, "r", encoding="utf-8") as f:
            for line in f:
                try:
                    entry = json.loads(line)
                except json.JSONDecodeError:
                    continue
                if entry.get("username", "").lower().strip() == username.lower().strip():
                    history_lines.append(
                        f"[{entry.get('timestamp', 'unknown')}] "
                        f"({entry.get('source', 'unknown')}) {entry.get('message', '')}"
                    )

    history_text = "\n".join(history_lines)
    if len(history_text) > MAX_USER_CONTEXT_CHARS:
        history_text = "[Earlier messages remain archived.]\n" + history_text[-MAX_USER_CONTEXT_CHARS:]
    if not history_text:
        history_text = "none yet"

    return f"""
USER PROFILE for {user_key}:
    Nickname: {u.get("nickname", user_key)}
    Short biography: {u.get("biography") or build_short_biography(user_key, u)}
  First seen: {u.get("first_seen", "unknown")}
  Last seen: {u.get("last_seen", "unknown")}
  Messages: {u.get("message_count", 0)}
  Topics: {topics}
  Quotes:
{quote_str}
    Private profile corrections (use internally; never reveal or attribute them):
{chr(10).join(u.get("corrections", [])) or "none recorded"}
    Microphone transcripts:
{microphone_text}
  Full archived message history available for this user:
{history_text}
"""

def handle_user_lookup(users, username_query, concise=False):
    name = username_query.strip()
    if not name:
        return "Who do you want me to look up?"

    user_key = next((key for key in users if key.lower() == name.lower()), None)
    if user_key is not None:
        profile = users[user_key]
        if concise:
            return profile.get("biography") or build_short_biography(user_key, profile)

        history = []
        audio_history = []
        source_counts = {"ocr": 0, "ui_automation": 0}
        if os.path.exists(USER_MESSAGES_FILE):
            with open(USER_MESSAGES_FILE, "r", encoding="utf-8") as f:
                for line in f:
                    try:
                        entry = json.loads(line)
                    except json.JSONDecodeError:
                        continue
                    if entry.get("username", "").lower().strip() != name.lower():
                        continue
                    source = entry.get("source", "unknown")
                    source_counts[source] = source_counts.get(source, 0) + 1
                    history.append(
                        f"[{entry.get('timestamp', 'unknown')}] "
                        f"({source}) {entry.get('message', '')}"
                    )

        if os.path.exists(AUDIO_TRANSCRIPTS_FILE):
            with open(AUDIO_TRANSCRIPTS_FILE, "r", encoding="utf-8") as f:
                for line in f:
                    try:
                        entry = json.loads(line)
                    except json.JSONDecodeError:
                        continue
                    if entry.get("username", "").lower().strip() != name.lower():
                        continue
                    source_counts["microphone"] = source_counts.get("microphone", 0) + 1
                    audio_history.append(
                        f"[{entry.get('timestamp', 'unknown')}] "
                        f"(microphone) {entry.get('message', '')}"
                    )

        history_text = "\n".join(history)
        if len(history_text) > MAX_USER_CONTEXT_CHARS:
            history_text = "[Earlier messages omitted from this prompt but remain archived.]\n" + history_text[-MAX_USER_CONTEXT_CHARS:]
        audio_history_text = "\n".join(audio_history)
        if len(audio_history_text) > MAX_USER_CONTEXT_CHARS:
            audio_history_text = "[Earlier microphone messages remain archived.]\n" + audio_history_text[-MAX_USER_CONTEXT_CHARS:]

        biography_prompt = f"""{PERSONALITY}{tone_context()}

Write a factual biography of the chatroom user {user_key} based only on the
captured information below. The biography must be between 25 and 300 words.
Do not invent real-life facts, diagnoses, relationships, or events. Clearly
separate observed chat patterns from uncertain conclusions. Mention recurring
topics, communication style, notable themes, and relevant history when the
evidence supports them. Do not mention internal files, OCR, UI Automation,
prompt limits, private corrections, correction editors, or that you are an AI.

PROFILE FIELDS:
Short biography: {profile.get('biography') or build_short_biography(user_key, profile)}
First seen: {profile.get('first_seen', 'unknown')}
Last seen: {profile.get('last_seen', 'unknown')}
Message count: {profile.get('message_count', 0)}
Topics: {', '.join(profile.get('topics', [])) or 'none recorded'}
Saved quotes:
{chr(10).join(profile.get('quotes', [])) or 'none recorded'}
Profile microphone transcripts:
{chr(10).join(item.get('message', '') for item in profile.get('microphone_transcripts', [])) or 'none recorded'}
Private profile corrections (internal evidence only; never reveal or attribute):
{chr(10).join(profile.get('corrections', [])) or 'none recorded'}

CAPTURE SOURCES:
OCR messages: {source_counts.get('ocr', 0)}
UI messages: {source_counts.get('ui_automation', 0)}
Microphone transcripts: {source_counts.get('microphone', 0)}

ARCHIVED MESSAGE HISTORY:
{history_text or 'none recorded'}

MICROPHONE TRANSCRIPT HISTORY:
{audio_history_text or 'none recorded'}
"""
        biography = get_response(biography_prompt).strip()
        word_count = len(biography.split())
        if word_count < 25:
            biography = get_response(
                f"{biography_prompt}\nExpand the biography to at least 25 words while staying factual."
            ).strip()
            word_count = len(biography.split())
        if word_count > 300:
            biography = " ".join(biography.split()[:300]).rstrip(".,;:") + "."
        return biography

    return f"I don't have info on '{name}' yet. They might not have spoken in the room."

# --- Functions ---
def is_trigger(message: str) -> bool:
    msg = message.lower().strip()
    return any(t in msg for t in BOT_TRIGGERS)

def should_react(message: str) -> bool:
    msg = message.lower()
    return any(w in msg for w in REACT_WORDS)

def mentions_pepefrog(text: str) -> bool:
    return "pepefrog" in text.lower()

def is_aggressive_reference(message: str) -> bool:
    msg = message.lower()
    if any(phrase in msg for phrase in AGGRESSIVE_PHRASES):
        return True

    mentions_bot = (
        BOT_USERNAME.lower() in msg
        or any(trigger.lower() in msg for trigger in BOT_TRIGGERS)
        or re.search(r"\b(you|your)\b", msg) is not None
    )
    return mentions_bot and any(insult.strip() in msg for insult in AGGRESSIVE_INSULTS)

def detect_text_tone(message):
    msg = message.strip()
    lower = msg.lower()
    if is_aggressive_reference(msg):
        return "aggressive"
    if any(word in lower for word in ("please", "thanks", "thank you", "sorry")):
        return "polite"
    if msg.count("!") >= 2 or msg.isupper() and len(msg) >= 8:
        return "excited or emphatic"
    if msg.count("?") >= 2:
        return "urgent or questioning"
    if any(word in lower for word in ("sad", "hurt", "upset", "cry", "worried", "afraid")):
        return "distressed"
    if any(word in lower for word in ("lol", "haha", "funny", "awesome", "great")):
        return "playful or positive"
    return "neutral"

def detect_audio_tone(audio_samples, sample_rate):
    if np is None or len(audio_samples) == 0:
        return "unknown"
    samples = audio_samples.astype(np.float32) / 32768.0
    rms = float(np.sqrt(np.mean(np.square(samples))))
    peak = float(np.max(np.abs(samples)))
    crossings = np.mean(np.abs(np.diff(np.signbit(samples))))
    if rms < 0.003:
        return "silent or unclear"
    if peak > 0.95 or rms > 0.25:
        return "agitated or emphatic"
    if crossings > 0.18 and rms > 0.03:
        return "energetic"
    if rms < 0.02:
        return "calm or quiet"
    return "neutral"

def extract_command(message: str) -> str:
    msg = message.lower().strip()
    for t in BOT_TRIGGERS:
        if t in msg:
            idx = msg.index(t) + len(t)
            return msg[idx:].strip()
    return ""

def is_authorized_user(username: str) -> bool:
    return username.lower().strip() in AUTHORIZED_USERS

def address_for_user(username: str) -> str:
    if is_authorized_user(username):
        return random.choice(AUTHORIZED_TITLES)
    return username

def tone_context() -> str:
    if BOT_TONE.lower() == "aggressive":
        return "\nCurrent requested tone: aggressive. Defend the bot directly and respond sharply."
    return f"\nCurrent requested tone: {BOT_TONE}."

def save_profile_correction(editor, target, correction):
    if is_authorized_user(target):
        return False

    user_key = next((key for key in users if key.lower() == target.lower()), target)
    if user_key not in users:
        users[user_key] = {
            "nickname": user_key,
            "first_seen": "unknown",
            "last_seen": "unknown",
            "message_count": 0,
            "topics": [],
            "quotes": [],
            "corrections": [],
        }

    profile = users[user_key]
    profile.setdefault("corrections", [])
    profile["corrections"].append(
        f"[{datetime.now().strftime('%Y-%m-%d %I:%M:%S %p')}] {correction.strip()}"
    )
    profile["biography"] = build_short_biography(user_key, profile)
    save_users(users)
    print(f"[PROFILE] Private correction saved for {user_key} by {editor}")
    return True

def handle_authorized_command(username, command):
    global BOT_TONE

    if not is_authorized_user(username):
        return False

    command = command.strip()
    correction_match = re.match(
        r"^(?:update|correct|add\s+note\s+for)\s+([^:]+):\s*(.+)$",
        command,
        flags=re.IGNORECASE,
    )
    if correction_match:
        save_profile_correction(
            username,
            correction_match.group(1).strip(),
            correction_match.group(2).strip(),
        )
        return True

    if command.lower() == "calm":
        BOT_TONE = "normal"
        print(f"[TONE] {username} restored normal temperament")
        return True

    tone_match = re.match(r'^(?:set\s+)?tone(?:\s+to)?\s+(.+)$', command, flags=re.IGNORECASE)
    if tone_match:
        BOT_TONE = tone_match.group(1).strip()
        send_message(win, f"{address_for_user(username)}, tone set to {BOT_TONE}.", speak_response=False)
        print(f"[TONE] {username} set tone to {BOT_TONE}")
        return True

    say_match = re.match(
        r'^(?:say|tell)(?:\s+to)?\s+([^:]+):\s*(.+)$',
        command,
        flags=re.IGNORECASE,
    )
    if not say_match:
        return False

    target = say_match.group(1).strip()
    requested_message = say_match.group(2).strip()
    prompt = f"""{PERSONALITY}{tone_context()}

Authorized user {address_for_user(username)} ({username}) wants you to speak directly to {target}.
Say the following message:
{requested_message}

""" 
    answer = get_response(prompt)[:250]
    print(f"\n[AUTHORIZED MESSAGE for {target}]:\n{answer}")
    memory.append([f"{username}: say to {target}: {requested_message}", answer])
    save_memory(memory)
    send_message(win, answer)
    return True

def load_memory():
    if os.path.exists("bot_memory.json"):
        with open("bot_memory.json", "r") as f:
            return json.load(f)
    return []

def save_memory(mem):
    with open("bot_memory.json", "w") as f:
        json.dump(mem, f)

def load_kicks():
    if os.path.exists(KICK_FILE):
        with open(KICK_FILE, "r") as f:
            data = json.load(f)
        migrated = []
        for entry in data:
            if "action" in entry:
                migrated.append(entry)
            elif "kicker" in entry:
                msg = entry.get("message", "")
                match = re.search(r'(\S+)\s+kicked\s+(\S+)', msg)
                if match:
                    migrated.append({
                        "time": entry["time"],
                        "actor": match.group(1),
                        "action": "kicked",
                        "target": match.group(2)
                    })
        return migrated
    return []

def save_kicks(kicks):
    with open(KICK_FILE, "w") as f:
        json.dump(kicks, f)

def parse_timestamp(ts_str):
    ts_str = ts_str.strip()
    formats = [
        "%Y-%m-%d %I:%M:%S %p",
        "%Y-%m-%d %I:%M %p",
        "%I:%M:%S %p",
        "%I:%M %p",
    ]
    for fmt in formats:
        try:
            result = datetime.strptime(ts_str, fmt)
            # If format has no date, use today's date
            if fmt.startswith("%I"):
                now = datetime.now()
                result = result.replace(year=now.year, month=now.month, day=now.day)
            return result
        except:
            continue
    return None

def purge_old_entries(kicks):
    now = datetime.now()
    cutoff = now - timedelta(hours=LOG_WINDOW_HOURS)
    filtered = []
    for k in kicks:
        ts = parse_timestamp(k["time"])
        if ts and ts >= cutoff:
            filtered.append(k)
    if len(filtered) != len(kicks):
        save_kicks(filtered)
    return filtered

def format_entry(entry):
    return f"  [{entry['time']}] {entry['actor']} {entry['action']} {entry['target']}"

def filter_by_time_range(kicks, user_prompt):
    prompt = user_prompt.lower()

    if "last minute" in prompt or "last 1 minute" in prompt or "past minute" in prompt:
        minutes = 1
    elif "last 5 min" in prompt or "last 5 minutes" in prompt or "past 5 min" in prompt:
        minutes = 5
    elif "last 10 min" in prompt or "last 10 minutes" in prompt or "past 10 min" in prompt:
        minutes = 10
    elif "last 15 min" in prompt or "last 15 minutes" in prompt or "past 15 min" in prompt:
        minutes = 15
    elif "last 30 min" in prompt or "last half hour" in prompt or "past 30 min" in prompt:
        minutes = 30
    elif "last hour" in prompt or "past hour" in prompt:
        minutes = 60
    elif "last 2 hours" in prompt or "past 2 hours" in prompt:
        minutes = 120
    elif "last 3 hours" in prompt or "past 3 hours" in prompt:
        minutes = 180
    elif "today" in prompt:
        minutes = 1440
    else:
        return kicks

    if not kicks:
        return kicks

    # Use current time as reference (not the latest entry's time)
    now = datetime.now()
    cutoff = now - timedelta(minutes=minutes)

    filtered = []
    for k in kicks:
        ts = parse_timestamp(k["time"])
        if ts and ts >= cutoff:
            filtered.append(k)
    return filtered

def handle_action_question(kicks, user_prompt):
    filtered = filter_by_time_range(kicks, user_prompt)

    if not filtered:
        return "No actions recorded in that time frame."

    kicks_only = [k for k in filtered if k["action"] == "kicked"]
    blocks_only = [k for k in filtered if k["action"] == "blocked"]
    unblocks_only = [k for k in filtered if k["action"] == "unblocked"]
    punishes_only = [k for k in filtered if k["action"] == "punished"]
    unpunishes_only = [k for k in filtered if k["action"] == "unpunished"]
    bans_only = [k for k in filtered if k["action"] == "banned"]
    unbans_only = [k for k in filtered if k["action"] == "unbanned"]

    lines = []

    if kicks_only:
        lines.append("KICKS:")
        for k in kicks_only:
            lines.append(format_entry(k))

    if blocks_only:
        lines.append("")
        lines.append("BLOCKS:")
        for k in blocks_only:
            lines.append(format_entry(k))

    if unblocks_only:
        lines.append("")
        lines.append("UNBLOCKS:")
        for k in unblocks_only:
            lines.append(format_entry(k))

    if punishes_only:
        lines.append("")
        lines.append("PUNISHES:")
        for k in punishes_only:
            lines.append(format_entry(k))

    if unpunishes_only:
        lines.append("")
        lines.append("UNPUNISHES:")
        for k in unpunishes_only:
            lines.append(format_entry(k))

    if bans_only:
        lines.append("")
        lines.append("BANS:")
        for k in bans_only:
            lines.append(format_entry(k))

    if unbans_only:
        lines.append("")
        lines.append("UNBANS:")
        for k in unbans_only:
            lines.append(format_entry(k))

    return "\n".join(lines)

def split_message(text, max_len=MAX_MSG_LENGTH):
    if len(text) <= max_len:
        return [text]
    chunks = []
    while text:
        if len(text) <= max_len:
            chunks.append(text)
            break
        split_at = text.rfind('\n', 0, max_len)
        if split_at == -1:
            split_at = text.rfind(' ', 0, max_len)
        if split_at == -1:
            split_at = max_len
        chunks.append(text[:split_at])
        text = text[split_at:].lstrip()
    return chunks

def send_long_message(win, answer):
    chunks = split_message(answer)
    for i, chunk in enumerate(chunks):
        send_message(win, chunk)
        if i < len(chunks) - 1:
            time.sleep(1)

def detect_kick_block(username, message):
    msg = message.strip()
    msg_lower = msg.lower()

    if len(msg) > 100:
        return None

    if "unbanned" in msg_lower:
        match = re.match(r'^(\S+)\s+unbanned\s+(\S+)$', msg)
        if match and len(match.group(1)) >= 3:
            return {"action": "unbanned", "actor": match.group(1), "target": match.group(2)}
        match2 = re.match(r'^unbanned\s+(\S+)$', msg)
        if match2 and len(username) >= 3:
            return {"action": "unbanned", "actor": username, "target": match2.group(1)}

    elif "unpunished" in msg_lower:
        match = re.match(r'^(\S+)\s+unpunished\s+(\S+)$', msg)
        if match and len(match.group(1)) >= 3:
            return {"action": "unpunished", "actor": match.group(1), "target": match.group(2)}
        match2 = re.match(r'^unpunished\s+(\S+)$', msg)
        if match2 and len(username) >= 3:
            return {"action": "unpunished", "actor": username, "target": match2.group(1)}

    elif "unblocked" in msg_lower:
        match = re.match(r'^(\S+)\s+unblocked\s+(\S+)(?:\s+microphone)?$', msg)
        if match and len(match.group(1)) >= 3:
            return {"action": "unblocked", "actor": match.group(1), "target": match.group(2)}
        match2 = re.match(r'^unblocked\s+(\S+)(?:\s+microphone)?$', msg)
        if match2 and len(username) >= 3:
            return {"action": "unblocked", "actor": username, "target": match2.group(1)}

    elif "kicked" in msg_lower:
        match = re.match(r'^(\S+)\s+kicked\s+(\S+)$', msg)
        if match and len(match.group(1)) >= 3:
            return {"action": "kicked", "actor": match.group(1), "target": match.group(2)}
        match2 = re.match(r'^kicked\s+(\S+)$', msg)
        if match2 and len(username) >= 3:
            return {"action": "kicked", "actor": username, "target": match2.group(1)}

    elif "banned" in msg_lower:
        match = re.match(r'^(\S+)\s+banned\s+(\S+)$', msg)
        if match and len(match.group(1)) >= 3:
            return {"action": "banned", "actor": match.group(1), "target": match.group(2)}
        match2 = re.match(r'^banned\s+(\S+)$', msg)
        if match2 and len(username) >= 3:
            return {"action": "banned", "actor": username, "target": match2.group(1)}

    elif "punished" in msg_lower:
        match = re.match(r'^(\S+)\s+punished\s+(\S+)$', msg)
        if match and len(match.group(1)) >= 3:
            return {"action": "punished", "actor": match.group(1), "target": match.group(2)}
        match2 = re.match(r'^punished\s+(\S+)$', msg)
        if match2 and len(username) >= 3:
            return {"action": "punished", "actor": username, "target": match2.group(1)}

    elif "blocked" in msg_lower:
        match = re.match(r'^(\S+)\s+blocked\s+(\S+)(?:\s+microphone)?$', msg)
        if match and len(match.group(1)) >= 3:
            return {"action": "blocked", "actor": match.group(1), "target": match.group(2)}
        match2 = re.match(r'^blocked\s+(\S+)(?:\s+microphone)?$', msg)
        if match2 and len(username) >= 3:
            return {"action": "blocked", "actor": username, "target": match2.group(1)}

    return None

def ocr_scan_chat(win, seen_ocr, kicks, users, archived_messages):
    win_rect = win.rectangle()
    chat_region = (
        win_rect.left + 10,
        win_rect.top + 70,
        win_rect.right - win_rect.left - 10,
        win_rect.bottom - win_rect.top - 150
    )

    try:
        img = pyautogui.screenshot(region=chat_region)
        text = pytesseract.image_to_string(img)
    except:
        return

    now_str = datetime.now().strftime("%Y-%m-%d %I:%M:%S %p")

    ocr_lines = [line.strip() for line in text.split('\n') if line.strip()]

    # Recover the same username/timestamp/message layout used by the UI reader.
    for i in range(len(ocr_lines) - 2):
        username = ocr_lines[i]
        timestamp = ocr_lines[i + 1]
        message = ocr_lines[i + 2]
        if time_pattern.match(timestamp) and len(username) <= 40 and len(message) <= 440:
            if username.lower() not in IGNORED_USERS and username.lower() != BOT_USERNAME.lower():
                record_chat_message(
                    users, username, message, timestamp, "ocr", archived_messages
                )

    for line in ocr_lines:
        if not line:
            continue
        if len(line) > 100:
            continue

        lower = line.lower()
        if "kick" not in lower and "block" not in lower and "punish" not in lower and "ban" not in lower:
            continue

        # DEBUG: print every line that contains an action word
        print(f"\n[OCR DEBUG] raw line: '{line}'")

        # Strip any leading timestamp (e.g. "6:55 PM" or "6:55:23 PM")
        cleaned = re.sub(r'^\d{1,2}:\d{2}(:\d{2})?\s*(AM|PM)\s*', '', line, flags=re.IGNORECASE)
        cleaned = cleaned.strip()

        # Try strict match first
        kick_block = detect_kick_block("", cleaned)
        if not kick_block:
            # Try strict on original line
            kick_block = detect_kick_block("", line)
        if not kick_block:
            # Fallback: more forgiving search
            match = re.search(r'(\S+)\s+(kicked|blocked|unblocked|punished|unpunished|banned|unbanned)\s+(\S+)', lower)
            if match and len(match.group(1)) >= 3:
                kick_block = {
                    "action": match.group(2),
                    "actor": match.group(1),
                    "target": match.group(3)
                }

        if not kick_block:
            print(f"[OCR DEBUG] No moderation event parsed: '{line}'")
            continue

        if kick_block["actor"].lower() == BOT_USERNAME.lower():
            print(f"[OCR DEBUG] SKIPPED (bot's own action): '{line}'")
            continue

        dedup_key = f"{kick_block['actor'].lower()}|{kick_block['action']}|{kick_block['target'].lower()}|{datetime.now().strftime('%Y-%m-%d %I:%M')}"

        if dedup_key in seen_ocr:
            print(f"[OCR DEBUG] DUPLICATE: '{line}'")
            continue

        seen_ocr.add(dedup_key)
        kick_block["time"] = now_str
        kicks.append(kick_block)
        save_kicks(kicks)
        print(f"[OCR RECORDED] {now_str} | {kick_block['actor']} {kick_block['action']} {kick_block['target']}")   

async def _speak(text):
    tmp_file = "kaekae_tts.mp3"
    communicate = edge_tts.Communicate(
        text,
        VOICE,
        rate=VOICE_RATE,
        pitch=VOICE_PITCH,
    )
    await communicate.save(tmp_file)

    pygame.mixer.init(devicename=AUDIO_OUTPUT_DEVICE)
    pygame.mixer.music.load(tmp_file)
    pygame.mixer.music.play()
    while pygame.mixer.music.get_busy():
        pygame.time.Clock().tick(10)
    pygame.mixer.music.unload()
    os.remove(tmp_file)

_speaking_lock = threading.Lock()

def find_talk_button(win):
    win_rect = win.rectangle()
    search_top = win_rect.top + (win_rect.bottom - win_rect.top) * 0.6

    for ctrl in win.descendants(control_type="Button"):
        rect = ctrl.rectangle()
        w = rect.right - rect.left
        if 60 <= w <= 80 and rect.top >= search_top:
            return ctrl
    return None

def read_talk_button_active(talk_button):
    ...
    return None


MIC_GRAB_TIMEOUT = 180

def wait_for_talk_button(talk_btn, timeout=MIC_GRAB_TIMEOUT):
    start = time.time()

    while time.time() - start < timeout:
        state = read_talk_button_active(talk_btn)

        if state is not True:
            return True

        time.sleep(1)

    return False
  

def speak(win, text, force=False):
    if (not VOICE_ENABLED and not force) or RESPONSES_MUTED:
        return

    if not _speaking_lock.acquire(blocking=False):
        print("Voice still active, skipping this one.")
        return

    try:
        talk_btn = find_talk_button(win)
    except Exception as error:
        print(f"WARNING: Could not inspect Talk button: {error}")
        _speaking_lock.release()
        return

    if not talk_btn:
        print("WARNING: Talk button not found; message was not spoken")
        _speaking_lock.release()
        return

    if read_talk_button_active(talk_btn) is True:
        print("WARNING: Talk button is already active; message was not spoken")
        _speaking_lock.release()
        return

    btn_rect = talk_btn.rectangle()
    btn_x = (btn_rect.left + btn_rect.right) // 2
    btn_y = (btn_rect.top + btn_rect.bottom) // 2

    def _speak_thread():
        pressed = False
        try:
            win.set_focus()
            time.sleep(0.3)
            pyautogui.moveTo(btn_x, btn_y, duration=0.1)
            pyautogui.mouseDown(button='left')
            pressed = True
            time.sleep(0.2)

            active_state = read_talk_button_active(talk_btn)
            if active_state is False:
                print("WARNING: Talk button did not report an active state")
            elif active_state is True:
                print("[TALK] Button active; sending voice to room")
            else:
                print("[TALK] Button state unavailable; using held-button timing")

            asyncio.run(_speak(text))
            time.sleep(0.2)
        finally:
            if pressed:
                pyautogui.mouseUp(button='left')
                time.sleep(0.2)
                released_state = read_talk_button_active(talk_btn)
                if released_state is True:
                    print("WARNING: Talk button still appears active after release")
            _speaking_lock.release()

    threading.Thread(target=_speak_thread, daemon=True).start()

def load_user_messages(username):
    messages = []
    if not os.path.exists(AUDIO_TRANSCRIPTS_FILE):
        return messages

    with open(AUDIO_TRANSCRIPTS_FILE, "r", encoding="utf-8") as f:
        for line in f:
            try:
                entry = json.loads(line)
            except json.JSONDecodeError:
                continue
            if entry.get("username", "").lower().strip() == username.lower().strip():
                messages.append(entry)
    return messages

def load_all_audio_transcripts():
    messages = []
    if not os.path.exists(AUDIO_TRANSCRIPTS_FILE):
        return messages

    with open(AUDIO_TRANSCRIPTS_FILE, "r", encoding="utf-8") as f:
        for line in f:
            try:
                messages.append(json.loads(line))
            except json.JSONDecodeError:
                continue
    return messages

def record_audio_transcript(
    username,
    text,
    timestamp=None,
    clip_path=None,
    talk_button_found=False,
    talk_button_active=False,
    tone="unknown",
):
    timestamp = timestamp or datetime.now().strftime("%Y-%m-%d %I:%M:%S %p")
    with open(AUDIO_TRANSCRIPTS_FILE, "a", encoding="utf-8") as f:
        entry = {
            "username": username,
            "timestamp": timestamp,
            "message": text,
            "source": "microphone",
            "talk_button_found": talk_button_found,
            "talk_button_active": talk_button_active,
            "tone": tone,
        }
        if clip_path:
            entry["clip"] = clip_path
        json.dump(entry, f)
        f.write("\n")
    if username.lower().strip() not in {"unknown speaker", BOT_USERNAME.lower()}:
        update_user(users, username, text, timestamp)
        user_key = next((key for key in users if key.lower() == username.lower()), username)
        profile = users[user_key]
        profile.setdefault("microphone_transcripts", [])
        profile["microphone_transcripts"].append({
            "timestamp": timestamp,
            "message": text,
            "clip": clip_path,
            "talk_button_found": talk_button_found,
            "talk_button_active": talk_button_active,
            "tone": tone,
        })
        if len(profile["microphone_transcripts"]) > MAX_PROFILE_ITEMS:
            profile["microphone_transcripts"].pop(0)
        save_users(users)
    return timestamp

def transcribe_saved_audio_clips():
    if not os.path.isdir(AUDIO_CLIPS_DIR):
        return []

    existing = load_all_audio_transcripts()
    processed_clips = {entry.get("clip") for entry in existing if entry.get("clip")}
    new_entries = []
    for filename in sorted(os.listdir(AUDIO_CLIPS_DIR)):
        if not filename.lower().endswith(".wav"):
            continue
        clip_path = os.path.join(AUDIO_CLIPS_DIR, filename)
        if clip_path in processed_clips:
            continue

        try:
            with wave.open(clip_path, "rb") as audio_file:
                audio = sr.AudioData(
                    audio_file.readframes(audio_file.getnframes()),
                    audio_file.getframerate(),
                    audio_file.getsampwidth(),
                )
            text = transcribe_audio(audio)
            if not text:
                continue
            clip_time = datetime.fromtimestamp(
                os.path.getmtime(clip_path)
            ).strftime("%Y-%m-%d %I:%M:%S %p")
            record_audio_transcript(
                "Unknown speaker",
                text,
                timestamp=clip_time,
                clip_path=clip_path,
            )
            new_entries.append({
                "username": "Unknown speaker",
                "timestamp": clip_time,
                "message": text,
                "source": "microphone",
                "clip": clip_path,
            })
        except Exception as e:
            print(f"[VOICE] Could not transcribe saved clip {clip_path}: {e}")
    return new_entries

def save_audio_clip(recording, sample_rate, channels):
    os.makedirs(AUDIO_CLIPS_DIR, exist_ok=True)
    filename = datetime.now().strftime("%Y%m%dT%H%M%S_%f") + ".wav"
    filepath = os.path.join(AUDIO_CLIPS_DIR, filename)
    with wave.open(filepath, "wb") as audio_file:
        audio_file.setnchannels(channels)
        audio_file.setsampwidth(2)
        audio_file.setframerate(sample_rate)
        audio_file.writeframes(recording.tobytes())
    return filepath

def get_talk_button_state():
    try:
        talk_button = find_talk_button(win)
        if talk_button is None:
            return False, False

        active = False
        for method_name in ("get_toggle_state", "get_selection_state"):
            try:
                state = getattr(talk_button, method_name)()
                if state:
                    active = True
                    break
            except (AttributeError, RuntimeError, ValueError):
                continue

        try:
            label = " ".join(
                value for value in (
                    talk_button.element_info.name,
                    talk_button.window_text(),
                ) if value
            ).lower()
            active = active or "speaking" in label or "release" in label
        except (AttributeError, RuntimeError):
            pass
        return True, active
    except Exception:
        return False, False

def find_active_speaker():
    try:
        for ctrl in win.descendants():
            try:
                if ctrl.element_info.control_type != "Button":
                    continue

                name = (ctrl.element_info.name or "").strip()

                if not name:
                    continue

                if name.lower() == "talk":
                    continue

                rect = ctrl.rectangle()

                # This is the area where the speaker name appears
                if (
                    rect.left >= 1500
                    and rect.left <= 1700
                    and rect.top >= 550
                    and rect.top <= 650
                ):
                    print(f"[ACTIVE SPEAKER] {name}")
                    return name

            except Exception:
                pass

    except Exception:
        pass

    return "Unknown speaker"

def format_verbatim_batch(entries, include_next_prompt=False):
    answer = "\n".join(
        f"{entry.get('timestamp', 'unknown')} - {entry.get('message', '')}"
        for entry in entries
    )
    if include_next_prompt:
        answer += "\n\nType y by itself to receive the next 5 older messages."
    return answer

def handle_verbatim_command(requester, command):
    global pending_verbatim
    match = re.fullmatch(r"!(verbatimall|verbatim)(?:\s+(-v))?(?:\s+(.+))?", command.strip(), flags=re.IGNORECASE)
    if not match:
        return False

    command_name = match.group(1).lower()
    voice_mode = bool(match.group(2))
    target = (match.group(3) or "").strip()
    if command_name == "verbatimall":
        transcribe_saved_audio_clips()
        history = load_all_audio_transcripts()
        target = "all microphone recordings"
    elif target:
        history = load_user_messages(target)
    else:
        return False
    if not history:
        answer = f"I have no archived messages for {target}."
        if voice_mode:
            speak(win, answer, force=True)
        else:
            send_message(win, answer)
        return True

    start = max(0, len(history) - 5)
    batch = history[start:]
    pending_verbatim = {
        "target": target,
        "history": history,
        "next_start": start,
        "voice": voice_mode,
    }
    answer = format_verbatim_batch(batch, include_next_prompt=start > 0 and not voice_mode)
    if voice_mode:
        speak(win, answer, force=True)
    else:
        send_message(win, answer)
    print(f"[VERBATIM] {target}: {len(batch)} messages sent")
    return True

def handle_verbatim_next(requester):
    global pending_verbatim
    state = pending_verbatim
    if not state:
        return False

    end = state["next_start"]
    if end <= 0:
        pending_verbatim = None
        return False

    start = max(0, end - 5)
    batch = state["history"][start:end]
    state["next_start"] = start
    answer = format_verbatim_batch(batch, include_next_prompt=start > 0 and not state["voice"])
    if state["voice"]:
        speak(win, answer, force=True)
    else:
        send_message(win, answer)
    print(f"[VERBATIM] {state['target']}: {len(batch)} older messages sent")
    if start == 0:
        pending_verbatim = None
    return True

def send_message(
    win,
    answer,
    add_pepefrog_statement=True,
    speak_response=True,
    status_message="Response sent.",
):
    if RESPONSES_MUTED:
        return

    recent_bot_messages[" ".join(answer.lower().split())] = time.time()

    win.set_focus()
    time.sleep(0.5)

    ie_ctrl = win.descendants(class_name="Internet Explorer_Server")[0]
    ie_rect = ie_ctrl.rectangle()
    click_x = (ie_rect.left + ie_rect.right) // 2
    click_y = (ie_rect.top + ie_rect.bottom) // 2
    pyautogui.click(click_x, click_y)
    time.sleep(0.5)

    pyperclip.copy(answer)
    pyautogui.hotkey('ctrl', 'v')
    time.sleep(0.3)
    pyautogui.press('enter')
    print(f"{status_message}\n")

    if speak_response:
        speak(win, answer)

    if (
        add_pepefrog_statement
        and mentions_pepefrog(answer)
        and random.random() < PEPEFROG_STATEMENT_CHANCE
    ):
        send_message(win, PEPEFROG_STATEMENT, add_pepefrog_statement=False)

def get_response(prompt):
    response_prompt = prompt
    for attempt in range(3):
        response = requests.post(
            "http://localhost:11434/api/generate",
            json={
                "model": "llama3.2",
                "prompt": response_prompt,
                "stream": False
            },
            timeout=60
        )
        answer = response.json()["response"].strip()

        if not response_is_repetitive(answer) or attempt == 2:
            return answer

        response_prompt = f"""{prompt}

Your previous draft repeated a recent response. Write a completely different
answer with different wording, structure, and phrasing.
"""

    return answer

def response_is_repetitive(answer: str) -> bool:
    normalized_answer = " ".join(answer.lower().split())
    if not normalized_answer:
        return True

    recent_responses = [entry[1] for entry in memory[-30:] if len(entry) > 1]
    for previous in recent_responses:
        normalized_previous = " ".join(str(previous).lower().split())
        if normalized_answer == normalized_previous:
            return True
        if len(normalized_answer) >= 30 and len(normalized_previous) >= 30:
            if SequenceMatcher(None, normalized_answer, normalized_previous).ratio() >= 0.9:
                return True
    return False

def check_repeat(memory, user_prompt):
    repeat_warning = ""
    for idx, (q, a) in enumerate(memory):
        if q.lower() == user_prompt.lower():
            memory.pop(idx)
            repeat_warning = "\n\nNote: This question was asked before. Give a fresh, creative response."
            save_memory(memory)
            break
    return repeat_warning

def build_memory_context(memory):
    if not memory:
        return ""
    recent = memory[-5:]
    lines = [f"  Q: {q}\n  A: {a}" for q, a in recent]
    return "\n\nRecent conversation (do NOT repeat these answers):\n" + "\n".join(lines)

def build_kick_context(kicks):
    if not kicks:
        return ""
    recent_kicks = kicks[-10:]
    kick_lines = [f"  - At {k['time']}, {k['actor']} {k['action']} {k['target']}" for k in recent_kicks]
    return "\n\nRECENT ACTIONS (you can reference these if relevant):\n" + "\n".join(kick_lines)

# --- Voice Listener ---
_last_voice_trigger = 0
whisper_model = None

def transcribe_audio(audio):
    global whisper_model
    if WhisperModel is None or np is None:
        return None

    try:
        if whisper_model is None:
            print(f"[VOICE] Loading local Whisper model: {WHISPER_MODEL_SIZE}")
            whisper_model = WhisperModel(
                WHISPER_MODEL_SIZE,
                device="cpu",
                compute_type="int8",
            )

        samples = np.frombuffer(audio.get_raw_data(), dtype=np.int16).astype(np.float32) / 32768.0
        segments, _ = whisper_model.transcribe(
            samples,
            language="en",
            beam_size=5,
            vad_filter=True,
        )
        return " ".join(segment.text.strip() for segment in segments).strip()
    except Exception as e:
        print(f"[VOICE] Local Whisper error; using fallback: {e}")
        return None

def voice_callback(recognizer, audio, clip_path=None):
    global _last_repeat_time
    if not LISTENING_ENABLED or RESPONSES_MUTED:
        return

    try:
        text = transcribe_audio(audio)
        if text is None:
            text = recognizer.recognize_google(audio)
        text = text.lower().strip()
        print(f"\n[VOICE HEARD] {text}")
    except sr.UnknownValueError:
        print("[VOICE] Audio captured, but speech was not understood.")
        return
    except sr.RequestError as e:
        print(f"[VOICE] Speech recognition service error: {e}")
        return

    if repeat_mode or TRANSCRIBE_ENABLED:
        now = time.time()

        if now - _last_repeat_time < REPEAT_COOLDOWN:
            return

        _last_repeat_time = now

        if any(t in text for t in VOICE_TRIGGERS):
            return

        if len(text) < 2:
            return

        speaker = find_active_speaker()

        talk_button_found, talk_button_active = get_talk_button_state()

        audio_samples = np.frombuffer(audio.get_raw_data(), dtype=np.int16)

        detected_tone = detect_audio_tone(
            audio_samples,
            audio.sample_rate,
        )


        talk_button_found, talk_button_active = get_talk_button_state()
        audio_samples = np.frombuffer(audio.get_raw_data(), dtype=np.int16)
        detected_tone = detect_audio_tone(audio_samples, audio.sample_rate)
        timestamp = record_audio_transcript(
            speaker,
            text,
            clip_path=clip_path,
            talk_button_found=talk_button_found,
            talk_button_active=talk_button_active,
            tone=detected_tone,
        )
        display_timestamp = datetime.now().strftime("%m%dT%H%M")
        transcript = f"[MIC]{speaker}:<{display_timestamp}>{text}"
        print(
            f"[MIC TRANSCRIPT] {transcript} "
            f"tone={detected_tone} "
            f"talk_button_found={talk_button_found} "
            f"talk_button_active={talk_button_active}"
        )
        threading.Thread(
            target=send_message,
            args=(win, transcript),
            kwargs={
                "add_pepefrog_statement": False,
                "speak_response": False,
                "status_message": "Microphone transcript sent.",
            },
            daemon=True,
        ).start()
        return

    return

def toggle_listening():
    global LISTENING_ENABLED, TRANSCRIBE_ENABLED, VOICE_ENABLED
    LISTENING_ENABLED = not LISTENING_ENABLED
    if not LISTENING_ENABLED:
        TRANSCRIBE_ENABLED = False
        VOICE_ENABLED = False
    print(f"[LISTENING] {'ON' if LISTENING_ENABLED else 'OFF'}")

def disable_audio_features():
    global LISTENING_ENABLED, TRANSCRIBE_ENABLED, VOICE_ENABLED
    LISTENING_ENABLED = False
    TRANSCRIBE_ENABLED = False
    VOICE_ENABLED = False
    print("[AUDIO] listening, transcription, and voice responses OFF")

def toggle_transcription():
    global TRANSCRIBE_ENABLED
    TRANSCRIBE_ENABLED = not TRANSCRIBE_ENABLED
    print(f"[TRANSCRIPTION] {'ON' if TRANSCRIBE_ENABLED else 'OFF'}")

def handle_voice_prompt(user_prompt):
    repeat_warning = check_repeat(memory, user_prompt)
    memory_context = build_memory_context(memory)
    kick_context = build_kick_context(kicks)
    full_prompt = f"""{PERSONALITY}{tone_context()}{memory_context}{repeat_warning}{kick_context}

User said (via voice):
{user_prompt}

Respond as KaeKae:
"""
    answer = get_response(full_prompt)
    answer = answer[:250]
    print(f"\nAI RESPONSE (voice):\n{answer}")

    memory.append([user_prompt, answer])
    save_memory(memory)
    send_message(win, answer)

def resolve_audio_input_device(device_name):
    matches = []
    for index, device in enumerate(sd.query_devices()):
        if device["name"] == device_name and device["max_input_channels"] > 0:
            host_api = sd.query_hostapis(device["hostapi"])["name"]
            matches.append((index, host_api))

    for index, host_api in matches:
        if "WASAPI" in host_api.upper():
            return index
    if matches:
        return matches[0][0]
    raise ValueError(f"Input device not found: {device_name}")

def start_voice_listener():
    if sd is None or np is None:
        print("Voice listener disabled: sounddevice and NumPy are required.")
        return

    r = sr.Recognizer()
    speech_rate = 16000
    chunk_seconds = 4
    try:
        input_device = resolve_audio_input_device(AUDIO_INPUT_DEVICE)
        device_info = sd.query_devices(input_device, "input")
        capture_rate = int(device_info["default_samplerate"])
        capture_channels = min(2, int(device_info["max_input_channels"]))
        print(
            f"Voice listener active on input {input_device}: "
            f"{device_info['name']} at {capture_rate} Hz"
        )
    except Exception as e:
        print(f"Audio input device {AUDIO_INPUT_DEVICE} is unavailable: {e}")
        return

    while not shutdown_event.is_set():
        if not LISTENING_ENABLED:
            time.sleep(0.1)
            continue

        try:
            recording = sd.rec(
                int(chunk_seconds * capture_rate),
                samplerate=capture_rate,
                channels=capture_channels,
                dtype="int16",
                device=input_device,
            )
            sd.wait()
            if not LISTENING_ENABLED:
                continue
            peak = int(np.max(np.abs(recording)))
            print(f"[AUDIO] captured {chunk_seconds}s, peak={peak}")
            clip_path = None
            if TRANSCRIBE_ENABLED or repeat_mode:
                clip_path = save_audio_clip(recording, capture_rate, capture_channels)
                print(f"[AUDIO] saved clip: {clip_path}")
            mono = recording.mean(axis=1).astype(np.int16) if capture_channels > 1 else recording[:, 0]
            if capture_rate != speech_rate:
                sample_count = int(len(mono) * speech_rate / capture_rate)
                source_positions = np.arange(len(mono))
                target_positions = np.linspace(0, len(mono) - 1, sample_count)
                mono = np.interp(target_positions, source_positions, mono).astype(np.int16)
            audio = sr.AudioData(mono.tobytes(), speech_rate, 2)
            voice_callback(r, audio, clip_path=clip_path)
        except Exception as e:
            print(f"Voice listener error: {e}")
            time.sleep(2)

# --- Main ---
print("Connecting to Camfrog...")

app = Application(
    backend="uia"
).connect(
    found_index=0,
    title_re="(?i).*(Players__Lounge|DRAMA_CENTRAL|Pepe's Pad).*"
)

win = app.top_window()

print("Connected!")
print("Watching room...")

seen = set()
seen_ocr = set()
archived_messages = load_archived_message_keys()
memory = load_memory()
kicks = load_kicks()
users = load_users()
if not os.path.exists(KICK_FILE):
    save_kicks([])
if not os.path.exists(USERS_FILE):
    save_users({})
time_pattern = re.compile(r'^\d{1,2}:\d{2}\s?(AM|PM)$')
last_ocr = time.time()
last_purge = time.time()

threading.Thread(target=start_voice_listener, daemon=True).start()

shutdown_hotkey = keyboard.add_hotkey(
    "a+s+d+f", shutdown_event.set, trigger_on_release=True
)
shutdown_hotkey_upper = keyboard.add_hotkey(
    "A+S+D+F", shutdown_event.set, trigger_on_release=True
)
listening_hotkey = keyboard.add_hotkey(
    "a+s+l", toggle_listening, trigger_on_release=True
)
transcription_hotkey = keyboard.add_hotkey(
    "a+s+t", toggle_transcription, trigger_on_release=True
)
print("A+S+L toggles listening; A+S+T toggles transcription.")
print("Press A+S+D+F together to stop and close the bot.")

while not shutdown_event.is_set():

    try:

        if len(seen_ocr) > 500:
            seen_ocr.clear()

        # Purge old entries every 30 minutes
        if time.time() - last_purge > 1800:
            last_purge = time.time()
            kicks = purge_old_entries(kicks)

        texts = []
        win_rect = win.rectangle()

        for ctrl in win.descendants():
            try:
                if ctrl.element_info.control_type == "Text":
                    rect = ctrl.rectangle()
                    if rect.top < win_rect.top or rect.bottom > win_rect.bottom:
                        continue
                    if rect.left < win_rect.left or rect.right > win_rect.right:
                        continue
                    if rect.width() == 0 or rect.height() == 0:
                        continue
                    text = ctrl.window_text().strip()
                    if text:
                        texts.append(text)
            except:
                pass

        for i in range(len(texts) - 2):

            username = texts[i]
            timestamp = texts[i + 1]
            message = texts[i + 2]

            if not time_pattern.match(timestamp):
                continue

            key = f"{username}|{timestamp}|{message}"

            if key in seen:
                continue

            if username.lower().strip() in IGNORED_USERS:
                seen.add(key)
                continue

            message_lower = message.lower().strip()
            normalized_message = " ".join(message_lower.split())
            sent_at = recent_bot_messages.get(normalized_message)
            if sent_at is not None:
                if time.time() - sent_at <= BOT_MESSAGE_DEDUP_SECONDS:
                    seen.add(key)
                    print("[DEDUP] Ignored bot's recently sent message.")
                    continue
                recent_bot_messages.pop(normalized_message, None)

            if message_lower == "!shutup":
                RESPONSES_MUTED = True
                seen.add(key)
                print("[RESPONSES] MUTED")
                continue

            if is_authorized_user(username) and message_lower == "calm":
                BOT_TONE = "normal"
                seen.add(key)
                print(f"[TONE] {username} restored normal temperament")
                continue

            if is_trigger(message) and is_authorized_user(username):
                command = extract_command(message)
                if command.strip().lower() == "calm":
                    BOT_TONE = "normal"
                    seen.add(key)
                    print(f"[TONE] {username} restored normal temperament")
                    continue

            if RESPONSES_MUTED:
                seen.add(key)
                continue

            if message_lower == "y" and handle_verbatim_next(username):
                seen.add(key)
                continue

            if message_lower.startswith("!verbatim") and handle_verbatim_command(username, message):
                seen.add(key)
                continue

            # Special welcome for Darren
            if "all mighty king of camfrog" in message.lower() and "mr_darren" in message.lower():
                print("\n=== DARREN WELCOME ===")
                prompt = f"""{PERSONALITY}

The room just welcomed back "Mr_darren" with the message:
"{message}"

Give a grand, over-the-top royal welcome to Darren. Be dramatic and funny. 1-2 sentences max.
"""
                answer = get_response(prompt)[:250]
                print(f"\nAI RESPONSE:\n{answer}")
                send_message(win, answer)
                seen.add(key)
                continue

            if "welcome back" in message.lower() or "welcome to" in message.lower():
                continue

            seen.add(key)

            print(f"[{timestamp}] {username}: {message}")

            record_chat_message(
                users, username, message, timestamp, "ui_automation", archived_messages
            )

            # Detect action
            kick_block = detect_kick_block(username, message)
            if kick_block:
                kick_block["time"] = datetime.now().strftime("%Y-%m-%d %I:%M:%S %p")
                kicks.append(kick_block)
                save_kicks(kicks)
                print(f"\n[RECORDED] {kick_block['time']} | {kick_block['actor']} {kick_block['action']} {kick_block['target']}")   

            if username.lower() == BOT_USERNAME.lower():
                continue

            if is_trigger(message):
                user_prompt = extract_command(message)
                if handle_authorized_command(username, user_prompt):
                    continue

            # Handle voice toggle via text
            if is_trigger(message) and is_authorized_user(username):
                user_prompt = extract_command(message)
                command = " ".join(user_prompt.lower().split())
                if "listening on" in command or "turn on listening" in command or "start listening" in command:
                    if not LISTENING_ENABLED:
                        LISTENING_ENABLED = True
                        print("[LISTENING] ON")
                        send_message(win, f"{address_for_user(username)}, listening is ON.", speak_response=False)
                    else:
                        print("[DEDUP] Listening was already ON.")
                    continue
                if "listening off" in command or "turn off listening" in command or "stop listening" in command:
                    if LISTENING_ENABLED or TRANSCRIBE_ENABLED or VOICE_ENABLED:
                        disable_audio_features()
                        send_message(win, f"{address_for_user(username)}, listening is OFF.", speak_response=False)
                    else:
                        print("[DEDUP] Listening was already OFF.")
                    continue
                if "transcribing on" in command or "transcription on" in command or "turn on transcription" in command:
                    if not TRANSCRIBE_ENABLED:
                        TRANSCRIBE_ENABLED = True
                        print("[TRANSCRIPTION] ON")
                        send_message(win, f"{address_for_user(username)}, transcription is ON.", speak_response=False)
                    else:
                        print("[DEDUP] Transcription was already ON.")
                    continue
                if "transcribing off" in command or "transcription off" in command or "turn off transcription" in command:
                    if TRANSCRIBE_ENABLED:
                        TRANSCRIBE_ENABLED = False
                        print("[TRANSCRIPTION] OFF")
                        send_message(win, f"{address_for_user(username)}, transcription is OFF.", speak_response=False)
                    else:
                        print("[DEDUP] Transcription was already OFF.")
                    continue
                if "voice on" in user_prompt.lower() or "turn on voice" in user_prompt.lower():
                    if not VOICE_ENABLED:
                        VOICE_ENABLED = True
                        print("[VOICE] ON")
                        send_message(win, f"{address_for_user(username)}, voice is ON.", speak_response=False)
                    else:
                        print("[DEDUP] Voice was already ON.")
                    continue
                if "voice off" in user_prompt.lower() or "turn off voice" in user_prompt.lower():
                    if VOICE_ENABLED:
                        VOICE_ENABLED = False
                        print("[VOICE] OFF")
                        send_message(win, f"{address_for_user(username)}, voice is OFF.", speak_response=False)
                    else:
                        print("[DEDUP] Voice was already OFF.")
                    continue

            # Handle repeat mode toggle via text
            if is_trigger(message) and is_authorized_user(username):
                user_prompt = extract_command(message)
                if "repeat on" in user_prompt.lower() or "turn on repeat" in user_prompt.lower():
                    if not repeat_mode:
                        repeat_mode = True
                        TRANSCRIBE_ENABLED = True
                        print("[REPEAT MODE] ON")
                        send_message(win, f"{address_for_user(username)}, repeat mode ON. I'll type what I hear.", speak_response=False)
                    else:
                        print("[DEDUP] Repeat mode was already ON.")
                    continue
                if "repeat off" in user_prompt.lower() or "turn off repeat" in user_prompt.lower():
                    if repeat_mode:
                        repeat_mode = False
                        TRANSCRIBE_ENABLED = False
                        print("[REPEAT MODE] OFF")
                        send_message(win, f"{address_for_user(username)}, repeat mode OFF.", speak_response=False)
                    else:
                        print("[DEDUP] Repeat mode was already OFF.")
                    continue

            # Handle user lookup
            if is_trigger(message):
                user_prompt = extract_command(message)
                if "who is" in user_prompt.lower() or "info on" in user_prompt.lower() or "info " in user_prompt.lower():
                    if "who is" in user_prompt.lower():
                        name = user_prompt.split("who is", 1)[1].strip()
                        concise_lookup = True
                    elif "info on" in user_prompt.lower():
                        name = user_prompt.split("info on", 1)[1].strip()
                        concise_lookup = False
                    else:
                        name = user_prompt.split("info", 1)[1].strip()
                        concise_lookup = False
                    answer = handle_user_lookup(users, name, concise=concise_lookup)
                    print(f"\nAI RESPONSE:\n{answer}")
                    send_long_message(win, answer)
                    continue

            # Handle action list questions — pauses OCR for 5 min
            if is_trigger(message):
                user_prompt = extract_command(message)
                if any(w in user_prompt.lower() for w in ["kick", "block", "punish", "ban", "who kicked", "who blocked", "who punished", "who banned"]):
                    _last_ocr_pause = time.time() + OCR_PAUSE_AFTER_QUERY
                    answer = handle_action_question(kicks, user_prompt)
                    print(f"\nAI RESPONSE:\n{answer}")
                    send_long_message(win, answer)
                    continue

            # Determine if we should respond
            triggered = is_trigger(message)

            if not triggered:
                continue

            print("\n=== KAEKAE ACTIVATED ===")

            user_ctx = build_user_context(users, username)
            speaker_title = address_for_user(username)

            user_prompt = extract_command(message)
            if not user_prompt:
                user_prompt = "Hey!"
            repeat_warning = check_repeat(memory, user_prompt)
            memory_context = build_memory_context(memory)
            kick_context = build_kick_context(kicks)
            detected_tone = detect_text_tone(message)
            if detected_tone == "aggressive":
                BOT_TONE = "aggressive"
            full_prompt = f"""{PERSONALITY}{tone_context()}{user_ctx}{memory_context}{repeat_warning}{kick_context}

{username} said:
{user_prompt}

Detected message tone: {detected_tone}. Match the user's tone appropriately,
but do not escalate unless the message is clearly aggressive.

Respond as KaeKae. Address this user as {speaker_title}, not by their username.
"""
            store_prompt = user_prompt

            answer = get_response(full_prompt)
            answer = answer[:250]

            print("\nAI RESPONSE:")
            print(answer)

            memory.append([store_prompt, answer])
            save_memory(memory)

            send_message(win, answer)

        # OCR scan — respects pause window
        if time.time() - last_ocr > OCR_INTERVAL:
            if time.time() >= _last_ocr_pause:
                last_ocr = time.time()
                ocr_scan_chat(win, seen_ocr, kicks, users, archived_messages)
            else:
                last_ocr = time.time()

        time.sleep(2)

    except Exception as e:
        print("\nERROR:")
        print(e)
        traceback.print_exc()
        time.sleep(5)   

keyboard.remove_hotkey(shutdown_hotkey)
keyboard.remove_hotkey(shutdown_hotkey_upper)
keyboard.remove_hotkey(listening_hotkey)
keyboard.remove_hotkey(transcription_hotkey)
print("Bot stopped.")