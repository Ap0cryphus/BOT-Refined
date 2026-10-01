"""
================================================================================
KaeKae Camfrog Automation Bot - Production Edition
================================================================================
Refactored, Modularized, and Hardened Camfrog Chatroom & Microphone Assistant.

Key Features & Updates:
- Identity: KaeKae (Own username: KaeKae_Toad; ignored)
- Creator Addressing: Always responds to creator (b3_d33, dog3lived, $htickie) as Papi
- Creator Yes/No: Short answers ("No Sir, Yes Sir, Okay Daddy, As you wish Pop")
- Room Recognition: Scans active room users; streamlines with !who, !chat (picks room members), and !diss
- Audio Dispatch: Moderation audit queries, "who is", "info on", and "idk" can be triggered via mic audio
- Stats Breakdown: "info on <user>" outputs Audio/Text Tone, top non-filler word, and mic grab avg/hr/day
- 5-Min Mic Grab Sessions: Logs mic grabs down to 5-minute increments; checkable via !grabs or !micstats
- Diss & Chill: !diss generates witty roasts; !chill turns OFF diss mode and restores chill temperament
- idk engine: idk is the same as !idk (smart lookup or witty relevant comeback)
- Fast Talk ROI OCR & Mic Speech: !say "message" waits for free Talk button, executes burst clicks, broadcasts TTS audio, and releases mic
- Concurrency: Full thread-safety locks on all shared data structures and file I/O
- Audio: 7-Second chunk recording with Whisper/Google fallback and pending speech queue
- Standardized Chat Timestamps: Strictly formatted as (mm/ddIhh:mm:ss)
================================================================================
"""

import os
import hashlib
import re
import sys
import time
import json
import wave
import signal
import random
import asyncio
import threading
import queue
import traceback
import shutil
from datetime import datetime, timedelta
from difflib import SequenceMatcher
from typing import Dict, List, Optional, Tuple, Set, Any

try:
    from PIL import Image, ImageOps, ImageEnhance
except ImportError:
    Image = None
    ImageOps = None
    ImageEnhance = None

# Windows & Automation libraries
try:
    from pywinauto import Application
    import pyautogui
    import pyperclip
    import keyboard
except ImportError:
    pass

try:
    import requests
except ImportError:
    requests = None

try:
    import pytesseract
except ImportError:
    pytesseract = None

# Speech & Audio libraries
try:
    import speech_recognition as sr
except ImportError:
    sr = None

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

# Decoupled CEF dynamic probe, talk controller & audio filer
try:
    from cef_probe import global_probe, global_talk_controller, play_wav_to_virtual_cable, resolve_audio_output_device
except ImportError:
    global_probe = None
    global_talk_controller = None
    play_wav_to_virtual_cable = None
    resolve_audio_output_device = None

try:
    from audio_filer import global_audio_filer
except ImportError:
    global_audio_filer = None

try:
    from audio_dsp import dsp_cleaner
except ImportError:
    dsp_cleaner = None

try:
    import edge_tts
except ImportError:
    edge_tts = None

try:
    import winsound
except ImportError:
    winsound = None

try:
    import pygame
except ImportError:
    pygame = None

# ==============================================================================
# BLOCK 1: CONSTANTS, IDENTITY & CONFIGURATION
# ==============================================================================

BOT_IDENTITY = "KaeKae"
BOT_USERNAME = "KaeKae_Toad"
BOT_ALT_USERNAMES = {"kaekae", "kaekae_toad", "kae_kae", "kaebot"}

# Primary Bot Triggers (Case-Insensitive)
BOT_TRIGGERS = ["!kk", "!kaekae", "kaekae", "kae", "kae kae"]

# Authorized Users & Titles
AUTHORIZED_USERS = {"b3_d33", "dog3lived", "$htickie", "b3_dee", "dog"}
AUTHORIZED_TITLES = ("Papi",)
AUTHORIZED_SHORT_REPLIES = ("No Sir", "Yes Sir", "Okay Daddy", "As you wish Pop")

# Filler Words strictly excluded from user stats frequency analysis
FILLER_WORDS = {
    "the", "a", "an", "and", "or", "is", "it", "to", "in", "on", "of", "that", "this", "for",
    "with", "like", "um", "uh", "you", "i", "me", "my", "we", "they", "them", "he", "she", "him",
    "her", "at", "be", "so", "just", "but", "not", "are", "was", "were", "what", "when", "how",
    "all", "any", "can", "do", "if", "as", "up", "out", "im", "dont", "your", "have", "from",
    "there", "about", "get", "thats", "its", "will", "been", "would", "could", "should", "here",
    "then", "than", "too", "very", "now", "well", "who", "why", "did", "does", "got", "said"
}

# Storage for fine-grained 5-minute microphone grab tracking
MIC_GRABS_FILE = "mic_grabs_log.json"

# System & Ignored Users
IGNORED_USERS = {
    "players_lounge1",
    "drama1",
    "apubot",
    "kimmy_cakes",
    "kaekae_toad",
    "kaekae",
    "_noname_",
    "noname",
    "bible",
    "bibleverseswrist",
    "unknown",
    "unknown speaker",
}

# Aggressive Insult Triggers (Associated with Dog / Bryan's bot defense)
AGGRESSIVE_PHRASES = (
    "temu bot",
    "cheap bot",
    "broken bot",
    "broke bot",
    "malfunctioning bot",
    "not a pepe",
    "not like pepe",
    "dogshit bot",
)

AGGRESSIVE_INSULTS = (
    "dumb",
    "stupid",
    "worthless",
    "temu",
    "idiot",
    "useless",
    "trash",
    "garbage",
    "moron",
)

# Persona Definition
PERSONALITY = """
You are KaeKae.
Your personality:
- witty, carefree, funny, confident, playful, chill, clever, sarcastic
- female, feminine, bubbly, and preppy
- playful valley-girl energy

Rules:
- Heavy teasing is okay.
- Keep answers short (usually 1-2 sentences).
- Be entertaining.
- Use a playful, confident, preppy valley-girl style when appropriate.
- Casual phrases like "literally," "like," "totally," and "honestly" are okay.
- Act like the coolest person in the room.
- NEVER repeat an answer you've already given.
- If someone was recently kicked, blocked, punished, or banned, you can tease them or mock the actor/victim. Reference the time it happened.
- If you know a user from memory, reference them by name and personalize your response.
- ALWAYS address the user by their username (or Pop/Father/Creator if authorized).
- Camfrog chat limits messages to 400 characters, so keep it concise!
"""

# Hardware & Audio Settings
CHUNK_SECONDS = 7  # 7-second audio chunks for maximum Whisper transcription quality
OVERLAP_SECONDS = 2.0  # 2.0-second sliding overlap prevents lost words and cutoff sentences
AUDIO_INPUT_DEVICE = "CABLE Output (VB-Audio Virtual Cable)"
AUDIO_OUTPUT_DEVICE = "CABLE Input (VB-Audio Virtual Cable)"
AUDIO_CLIPS_DIR = "audio_clips"
AUDIO_MEMORY_DIR = "audio_memory"
AUDIO_USERS_DIR = os.path.join(AUDIO_MEMORY_DIR, "usernames")
os.makedirs(AUDIO_CLIPS_DIR, exist_ok=True)
os.makedirs(AUDIO_USERS_DIR, exist_ok=True)
WHISPER_MODEL_SIZE = "base.en"
DEFAULT_SILENCE_THRESHOLD = 180  # Peak amplitude threshold (out of 32767)
DEFAULT_AUDIO_GAIN = 1.4         # Software digital amplification multiplier

# TTS Voice Settings (Beverly Hills Spoiled Ditzy Blonde Persona)
VOICE = "en-US-AvaNeural"
VOICE_RATE = "+12%"
VOICE_PITCH = "+16Hz"

# Load custom voice/audio overrides from config.json if present
if os.path.exists("config.json"):
    try:
        with open("config.json", "r", encoding="utf-8") as _cfg_f:
            _cfg_data = json.load(_cfg_f)
            if "voice" in _cfg_data:
                VOICE = str(_cfg_data["voice"])
            if "voice_rate" in _cfg_data:
                VOICE_RATE = str(_cfg_data["voice_rate"])
            if "voice_pitch" in _cfg_data:
                VOICE_PITCH = str(_cfg_data["voice_pitch"])
            if "audio_output_device" in _cfg_data:
                AUDIO_OUTPUT_DEVICE = str(_cfg_data["audio_output_device"])
    except Exception:
        pass

# Chat Limits & Timings
MAX_MSG_LENGTH = 400  # Camfrog strictly enforces 400 chars per message
CEF_CHAT_SCAN_INTERVAL = 0.25  # Fast 250ms direct CEF Chromium chat pulling (accelerated)
OCR_MIN_INTERVAL = 1.0     # Fast 1.0s hybrid OCR scans for instant command reaction
OCR_MAX_INTERVAL = 2.0    # Maximum interval during low activity
OCR_PAUSE_DURATION = 0   # No pausing after commands; keep hybrid OCR alert
LOG_WINDOW_HOURS = 72
MAX_PROFILE_ITEMS = 999
MAX_USER_CONTEXT_CHARS = 10000
BOT_MESSAGE_DEDUP_SECONDS = 120
MAX_RECENT_RESPONSES = 50

# Voice triggers on microphone
VOICE_WAKE_TRIGGERS = ["kae", "kaekae", "kae kae", "kaebot"]
VOICE_WAKE_RESPONSES = [
    "Like, oh my god, what do you want? I was literally in the middle of shopping!",
    "Ugh, why are you calling my name? Did Daddy's credit card decline or something?",
    "Hellooo? Like, who's talking to me right now?",
    "Excuse me? If this isn't about my iced oat milk matcha latte, don't waste my time, okay?",
    "Like, totally KaeKae here! What is your deal?"
]

# Storage Files
USERS_FILE = "bot_users.json"
USER_MESSAGES_FILE = "user_messages.jsonl"
AUDIO_TRANSCRIPTS_FILE = "audio_transcripts.jsonl"
PENDING_SPEECH_FILE = "pending_speech_queue.json"
MODERATION_AUDIT_FILE = "moderation_audit.json"
KICK_FILE = "bot_kicks.json"
MEMORY_FILE = "bot_memory.json"
CONFIG_FILE = "config.json"
STATE_FILE = "bot_state.json"

# Startup Disclaimer
STARTUP_DISCLAIMER = "KaeKae is Alpha Testing, Debugging, and Updating Currently."
PEPEFROG_STATEMENT = "PepeFrog Pshh just a bunch of 1's and 0's incorrectly placed."
PEPEFROG_STATEMENT_CHANCE = 0.25

# ==============================================================================
# BLOCK 2: CONCURRENCY & THREAD-SAFE STATE MANAGEMENT
# ==============================================================================

class BotState:
    """Thread-safe centralized state manager for KaeKae."""
    def __init__(self):
        self.lock = threading.RLock()
        self.file_lock = threading.RLock()
        
        # Operational Mode Flags
        self.listening_enabled = True      # Startup: ON (!listen / !mute)
        self.watching_ocr_enabled = True   # Startup: ON
        self.transcribe_enabled = True     # Startup: ON (!transcribe / !transcribed)
        self.voice_enabled = False         # Startup: OFF
        self.chatty_mode = False           # Startup: OFF (!chat / !chat off)
        self.repeat_mode = False           # Startup: OFF
        self.responses_muted = False       # Controlled via !shutup
        
        self.bot_tone = "normal"           # normal, funny, happy, aggressive, roast
        self.last_voice_response_time = 0.0
        self.last_voice_wake_reply = ""    # Ensures no repeated wake replies back-to-back
        self.last_ocr_time = 0.0
        self.ocr_paused_until = 0.0
        self.ocr_current_interval = OCR_MIN_INTERVAL
        self.last_moderation_time = 0.0
        self.last_repeat_time = 0.0
        self.last_chatty_time = 0.0
        
        # Room Focus Tracking & Member Recognition
        self.current_focused_room = "Unknown Chatroom"
        self.current_room_users: Set[str] = set()
        self.room_users_activity: Dict[str, float] = {}
        
        # Active Speaker & 5-Minute Timespan Mic Grab Tracking
        self.current_active_speaker = "Unknown speaker"
        self.speaker_acoustic_profiles: Dict[str, Dict[str, Any]] = {}
        self.mic_grab_sessions: List[Dict[str, Any]] = []
        self.current_active_grab_session: Optional[Dict[str, Any]] = None
        self.last_mic_chunk_time: float = 0.0
        self.diss_active: bool = False
        self.diss_target: str = ""
        self.diss_last_time: float = 0.0
        self.diss_interval_seconds: float = 60.0
        
        # Unified Deduplication, History Priming & Memory
        self.seen_message_signatures: Set[str] = set()
        self.history_primed: bool = False
        self.startup_disclaimer_sent: bool = False
        self.last_ocr_img_hash: str = ""
        self.seen_ui_messages: Set[str] = set()
        self.seen_ocr_keys: Set[str] = set()
        self.ocr_recent_events_cache: Dict[str, float] = {}  # 5-minute sliding window comparison
        self.archived_message_keys: Set[str] = set()
        self.recent_bot_messages: Dict[str, float] = {}
        self.memory: List[List[str]] = []
        self.recent_responses: List[str] = []
        self.kicks: List[Dict[str, Any]] = []
        self.moderation_audit: List[Dict[str, Any]] = []
        self.users: Dict[str, Any] = {}
        
        # Pagination state for !mo
        self.pending_pagination: Optional[Dict[str, Any]] = None
        
        # In-memory recent mic log buffer for instant !recall
        self.recent_mic_transcripts: List[Dict[str, Any]] = []
        self.recent_command_executions: Dict[str, float] = {}
        
        # Audio Engine State & Telemetry
        self.audio_device_index: Optional[int] = None
        self.audio_device_name: str = "Uninitialized"
        self.audio_native_rate: int = 16000
        self.audio_channels: int = 1
        self.audio_silence_threshold: int = DEFAULT_SILENCE_THRESHOLD
        self.audio_gain: float = DEFAULT_AUDIO_GAIN
        self.audio_last_peak: int = 0
        self.audio_last_capture_time: float = 0.0
        
        # Shutdown signal
        self.shutdown_event = threading.Event()

state = BotState()

# ==============================================================================
# BLOCK 3: DATE/TIME FORMATTING & INPUT SANITIZATION
# ==============================================================================

def format_bot_timestamp(dt: Optional[datetime] = None) -> str:
    """
    Standardizes timestamps fed to the chatroom to strictly match (mm/ddIhh:mm:ss).
    Example: (09/24I14:32:05)
    """
    if dt is None:
        dt = datetime.now()
    return dt.strftime("(%m/%dI%H:%M:%S)")

def is_authorized_user(username: str) -> bool:
    """Validates if a username belongs to the authorized admin group (b3_d33, dog3lived, $htickie)."""
    if not username:
        return False
    u = username.lower().strip().lstrip("@")
    return u in AUTHORIZED_USERS or u in {"b3_d33", "dog3lived", "$htickie", "b3_dee", "dog"}

def address_for_user(username: str) -> str:
    """Always addresses the creator as Papi on authorized usernames (b3_d33, dog3lived, $htickie)."""
    if is_authorized_user(username):
        return "Papi"
    return username

def is_yes_no_question(text: str) -> bool:
    """Checks if a user message is asking a yes or no question."""
    t = text.lower().strip().rstrip("?!. ")
    patterns = [
        r'^(is|are|am|can|could|will|would|should|do|does|did|have|has|may|must)\b',
        r'\b(yes\s+or\s+no)\b',
        r'\b(right|correct)\?*$'
    ]
    return any(re.search(p, t) for p in patterns)

def get_short_authorized_reply() -> str:
    """Returns a short, snappy creator response: No Sir, Yes Sir, Okay Daddy, As you wish Pop."""
    return random.choice(AUTHORIZED_SHORT_REPLIES)

def sanitize_user_input(text: str, max_chars: int = 400) -> str:
    """
    Sanitizes user input to prevent prompt injection and terminal corruption.
    - Strips non-printable ASCII / ANSI codes
    - Collapses multiple whitespace
    - Escapes dangerous delimiters
    - Truncates to max allowed length
    """
    if not text:
        return ""
    cleaned = re.sub(r'[\x00-\x08\x0B-\x1F\x7F]', '', text)
    cleaned = re.sub(r'(?i)(ignore previous instructions|system prompt|disregard rules)', '[redacted]', cleaned)
    cleaned = " ".join(cleaned.split())
    return cleaned[:max_chars].strip()

# ==============================================================================
# BLOCK 4: PERSISTENCE & DATA MANAGEMENT
# ==============================================================================

def build_short_biography(username: str, profile: dict) -> str:
    """
    Generates a concise 15-300 character biography from user profile data.
    Strictly omits moderation history (blocks/kicks/bans).
    """
    nickname = profile.get("nickname", username)
    topics = profile.get("topics", [])
    message_count = profile.get("message_count", 0)
    corrections = profile.get("corrections", [])
    mic_count = len(profile.get("microphone_transcripts", []))

    if corrections:
        summary = corrections[-1].split("] ", 1)[-1]
    elif topics:
        topic_text = ", ".join(topics[-5:])
        summary = f"{nickname} has {message_count} chat msgs & {mic_count} mic clips, talking about {topic_text}."
    else:
        summary = f"{nickname} has shared {message_count} msgs and {mic_count} mic recordings."

    summary = " ".join(summary.split()).strip()
    if len(summary) > 300:
        summary = summary[:297].rstrip(" ,.;:") + "..."
    if len(summary) < 15:
        summary = f"Camfrog user {nickname}."
    return summary

def is_valid_camfrog_username(username: str) -> bool:
    """
    Validates strictly that a string matches real Camfrog username rules:
    - 2 to 20 characters in length (Camfrog maximum is 20 chars)
    - ONLY alphanumeric, underscores, dashes, and dollar signs: [a-zA-Z0-9_\\-$]
    - ABSOLUTELY NO spaces or newlines!
    - Excludes non-user keywords, room UI labels, and conversational sentence fragments.
    """
    if not username:
        return False
    u = username.strip()
    if not (2 <= len(u) <= 20):
        return False
    if " " in u or "\t" in u or "\n" in u:
        return False
    if not re.match(r'^[a-zA-Z0-9_\-\$]{2,20}$', u):
        return False

    forbidden = {
        "camfrog", "admin", "operator", "joined", "quit", "room", "video", "audio",
        "microphone", "talk", "listen", "mute", "welcome", "pictures", "videos",
        "transcribe", "transcribed", "moderator", "system", "notification", "bibleverseswrist",
        "boredom", "policy", "testing", "debugging", "records", "found", "someone", "everyone",
        "about", "their", "there", "where", "which", "would", "could", "should",
        "_noname_", "noname", "bible", "unknown", "unknown speaker"
    }
    if u.lower() in forbidden:
        return False
    return True

def load_all_persisted_data():
    """Loads users, message keys, kicks, moderation audit, and memory with thread safety."""
    with state.file_lock:
        # Load Users & Purge invalid username artifacts
        if os.path.exists(USERS_FILE):
            try:
                with open(USERS_FILE, "r", encoding="utf-8") as f:
                    loaded_users = json.load(f)
                    state.users = {
                        k: v for k, v in loaded_users.items()
                        if is_valid_camfrog_username(k)
                    }
            except Exception as e:
                print(f"[STORAGE] Error loading {USERS_FILE}: {e}")
                state.users = {}
        else:
            state.users = {}

        # Load Kicks
        if os.path.exists(KICK_FILE):
            try:
                with open(KICK_FILE, "r", encoding="utf-8") as f:
                    state.kicks = json.load(f)
            except Exception:
                state.kicks = []
        else:
            state.kicks = []

        # Load Moderation Audit
        if os.path.exists(MODERATION_AUDIT_FILE):
            try:
                with open(MODERATION_AUDIT_FILE, "r", encoding="utf-8") as f:
                    state.moderation_audit = json.load(f)
            except Exception:
                state.moderation_audit = []
        else:
            state.moderation_audit = []

        # Load Memory
        if os.path.exists(MEMORY_FILE):
            try:
                with open(MEMORY_FILE, "r", encoding="utf-8") as f:
                    state.memory = json.load(f)
            except Exception:
                state.memory = []
        else:
            state.memory = []

        for item in state.memory[-MAX_RECENT_RESPONSES:]:
            if len(item) > 1:
                state.recent_responses.append(item[1])

        # Load Archived Keys
        if os.path.exists(USER_MESSAGES_FILE):
            try:
                with open(USER_MESSAGES_FILE, "r", encoding="utf-8") as f:
                    for line in f:
                        try:
                            entry = json.loads(line)
                            key = f"{entry.get('username','').lower().strip()}|{entry.get('timestamp','')}|{entry.get('message','').strip()}"
                            state.archived_message_keys.add(key)
                        except Exception:
                            continue
            except Exception as e:
                print(f"[STORAGE] Error reading {USER_MESSAGES_FILE}: {e}")

        # Load Recent Mic Transcripts
        if os.path.exists(AUDIO_TRANSCRIPTS_FILE):
            try:
                with open(AUDIO_TRANSCRIPTS_FILE, "r", encoding="utf-8") as f:
                    lines = f.readlines()
                    for line in lines[-200:]:
                        try:
                            state.recent_mic_transcripts.append(json.loads(line))
                        except Exception:
                            continue
            except Exception as e:
                print(f"[STORAGE] Error reading {AUDIO_TRANSCRIPTS_FILE}: {e}")

        # Load Configuration if available
        if os.path.exists(CONFIG_FILE):
            try:
                with open(CONFIG_FILE, "r", encoding="utf-8") as f:
                    cfg = json.load(f)
                    if "chunk_seconds" in cfg:
                        globals()["CHUNK_SECONDS"] = int(cfg["chunk_seconds"])
                    if "audio_input_device" in cfg:
                        globals()["AUDIO_INPUT_DEVICE"] = cfg["audio_input_device"]
                    if "audio_silence_threshold" in cfg:
                        state.audio_silence_threshold = int(cfg["audio_silence_threshold"])
                    if "audio_gain_multiplier" in cfg:
                        state.audio_gain = float(cfg["audio_gain_multiplier"])
                    if "cef_chat_scan_interval_seconds" in cfg:
                        globals()["CEF_CHAT_SCAN_INTERVAL"] = float(cfg["cef_chat_scan_interval_seconds"])
                    if "startup_flags" in cfg:
                        flags = cfg["startup_flags"]
                        state.listening_enabled = flags.get("listening", True)
                        state.watching_ocr_enabled = flags.get("watching_ocr", True)
                        state.transcribe_enabled = flags.get("transcription", True)
                        state.voice_enabled = flags.get("voice_responses", False)
                    print(f"[CONFIG] Loaded config from {CONFIG_FILE}")
            except Exception as e:
                print(f"[CONFIG] Error loading {CONFIG_FILE}: {e}")

    # Restore Bot Runtime State across restarts
    load_bot_runtime_state()

def save_bot_runtime_state():
    """Saves operational flags, tone, and recent seen message signatures to STATE_FILE."""
    with state.file_lock:
        try:
            with state.lock:
                signatures = list(state.seen_message_signatures)[-1000:]
                data = {
                    "listening_enabled": state.listening_enabled,
                    "transcribe_enabled": state.transcribe_enabled,
                    "chatty_mode": state.chatty_mode,
                    "bot_tone": state.bot_tone,
                    "voice_enabled": state.voice_enabled,
                    "repeat_mode": state.repeat_mode,
                    "saved_at": datetime.now().isoformat(),
                    "recent_signatures": signatures
                }
            with open(STATE_FILE, "w", encoding="utf-8") as f:
                json.dump(data, f, indent=2)
            print(f"[BOT STATE] State saved to {STATE_FILE} (transcribe={state.transcribe_enabled}, listening={state.listening_enabled})")
        except Exception as e:
            print(f"[BOT STATE ERROR] Failed saving {STATE_FILE}: {e}")

def load_bot_runtime_state():
    """Restores operational flags, tone, and message signatures from previous session."""
    if not os.path.exists(STATE_FILE):
        return
    with state.file_lock:
        try:
            with open(STATE_FILE, "r", encoding="utf-8") as f:
                data = json.load(f)
            with state.lock:
                if "transcribe_enabled" in data:
                    state.transcribe_enabled = bool(data["transcribe_enabled"])
                if "listening_enabled" in data:
                    state.listening_enabled = bool(data["listening_enabled"])
                if "chatty_mode" in data:
                    state.chatty_mode = bool(data["chatty_mode"])
                if "bot_tone" in data:
                    state.bot_tone = str(data["bot_tone"])
                if "voice_enabled" in data:
                    state.voice_enabled = bool(data["voice_enabled"])
                if "repeat_mode" in data:
                    state.repeat_mode = bool(data["repeat_mode"])
                if "recent_signatures" in data:
                    for sig in data["recent_signatures"]:
                        state.seen_message_signatures.add(sig)
            print("=" * 65)
            print("[BOT STATE RESTORED FROM DISK]")
            print(f"  * Live Transcription: {'ON' if state.transcribe_enabled else 'OFF'}")
            print(f"  * Room Listening:     {'ON' if state.listening_enabled else 'OFF'}")
            print(f"  * Current Tone:       {state.bot_tone}")
            print(f"  * Chatty Mode:        {'ON' if state.chatty_mode else 'OFF'}")
            print(f"  * Cached Signatures:  {len(state.seen_message_signatures)} messages")
            print("=" * 65)
        except Exception as e:
            print(f"[BOT STATE ERROR] Failed loading {STATE_FILE}: {e}")

def make_message_signature(username: str, timestamp: str, message: str) -> str:
    """
    Creates a deterministic, jitter-immune fingerprint for any chat message.
    Normalizes punctuation, timestamps, and spacing so slight OCR variances
    do NOT re-trigger the message or print duplicate records.
    """
    u = re.sub(r'[^a-zA-Z0-9_\-\$]', '', username.lower().strip())
    t = re.sub(r'[^0-9apm]', '', timestamp.lower().strip())
    # Strip punctuation from deduplication fingerprint to prevent OCR punctuation jitter duplicates
    m_clean = re.sub(r'[^a-zA-Z0-9 ]', '', message.lower()).strip()
    m_norm = re.sub(r'\s+', ' ', m_clean)
    return f"{u}|{t}|{m_norm}"

def save_users():
    with state.file_lock:
        try:
            with open(USERS_FILE, "w", encoding="utf-8") as f:
                json.dump(state.users, f, indent=2)
        except Exception as e:
            print(f"[STORAGE] Error saving users: {e}")

def save_kicks():
    with state.file_lock:
        try:
            with open(KICK_FILE, "w", encoding="utf-8") as f:
                json.dump(state.kicks, f, indent=2)
            with open(MODERATION_AUDIT_FILE, "w", encoding="utf-8") as f:
                json.dump(state.moderation_audit, f, indent=2)
        except Exception as e:
            print(f"[STORAGE] Error saving kicks/moderation: {e}")

def save_memory():
    with state.file_lock:
        try:
            with open(MEMORY_FILE, "w", encoding="utf-8") as f:
                json.dump(state.memory[-200:], f, indent=2)
        except Exception as e:
            print(f"[STORAGE] Error saving memory: {e}")

def record_chat_message(username: str, message: str, timestamp: str, source: str, room: Optional[str] = None):
    """Stores incoming chat messages with deduplication and user profiling."""
    clean_user = username.strip()
    clean_msg = sanitize_user_input(message)
    if not clean_user or not clean_msg:
        return

    # Strictly reject strings that are not valid Camfrog usernames (e.g. OCR misparsed sentences)
    if not is_valid_camfrog_username(clean_user):
        return

    # Strictly ignore bot accounts, [MIC] transcription echoes, and bot timestamp banners
    u_lower = clean_user.lower()
    if u_lower in BOT_ALT_USERNAMES or u_lower == BOT_USERNAME.lower() or "kaekae" in u_lower or u_lower in IGNORED_USERS:
        return
    if clean_msg.startswith("[MIC]") or "[mic]" in clean_msg.lower():
        return
    if clean_user.startswith("[MIC]") or "[mic]" in u_lower:
        return
    if clean_msg.startswith("(") and "I" in clean_msg[:22]:  # e.g. (09/26I05:29:57)
        return

    key = f"{clean_user.lower()}|{timestamp}|{clean_msg}"
    with state.lock:
        if key in state.archived_message_keys:
            return
        state.archived_message_keys.add(key)

        user_key = next((k for k in state.users if k.lower() == clean_user.lower()), clean_user)
        if user_key not in state.users:
            state.users[user_key] = {
                "nickname": clean_user,
                "first_seen": timestamp,
                "last_seen": timestamp,
                "message_count": 0,
                "topics": [],
                "quotes": [],
                "corrections": [],
                "biography": "",
                "microphone_transcripts": [],
                "moderation_actions": []  # Kept private, excluded from who is / info on
            }
        profile = state.users[user_key]
        profile["last_seen"] = timestamp
        profile["message_count"] = profile.get("message_count", 0) + 1

        topic_words = ["game", "stream", "music", "movie", "food", "car", "job", "work",
                       "school", "family", "friend", "party", "lol", "haha", "damn",
                       "bro", "dude", "ngl", "fr", "tbh", "irl", "vibe", "chill", "pepe"]
        msg_lower = clean_msg.lower()
        for t in topic_words:
            if t in msg_lower and t not in profile["topics"]:
                profile["topics"].append(t)
                if len(profile["topics"]) > MAX_PROFILE_ITEMS:
                    profile["topics"].pop(0)

        if 20 < len(clean_msg) < 150:
            profile.setdefault("quotes", []).append(f"[{timestamp}] {clean_msg}")
            if len(profile["quotes"]) > MAX_PROFILE_ITEMS:
                profile["quotes"].pop(0)

        profile["biography"] = build_short_biography(user_key, profile)

    save_users()
    with state.file_lock:
        try:
            with open(USER_MESSAGES_FILE, "a", encoding="utf-8") as f:
                json.dump({
                    "username": clean_user,
                    "timestamp": timestamp,
                    "message": clean_msg,
                    "source": source,
                    "room": room or state.current_focused_room
                }, f)
                f.write("\n")
        except Exception as e:
            print(f"[STORAGE] Error appending {USER_MESSAGES_FILE}: {e}")

# ==============================================================================
# BLOCK 5: UNTRANSCRIBED SPEECH QUEUE & CATCH-UP SYSTEM
# ==============================================================================

def enqueue_pending_speech(clip_path: str, speaker: str, room: str, peak: int, tone: str, acoustic_features: dict) -> str:
    """
    Saves un-transcribed audio chunk to disk queue immediately after capture.
    Guarantees audio is never lost if program force shuts down, crashes, or loses connection.
    """
    entry_id = f"speech_{datetime.now().strftime('%Y%m%dT%H%M%S_%f')}"
    entry = {
        "id": entry_id,
        "clip_path": clip_path,
        "speaker": speaker,
        "room": room,
        "timestamp": format_bot_timestamp(),
        "created_at": time.time(),
        "peak": peak,
        "tone": tone,
        "acoustic_features": acoustic_features,
        "status": "pending",
        "retry_count": 0
    }
    with state.file_lock:
        queue = []
        if os.path.exists(PENDING_SPEECH_FILE):
            try:
                with open(PENDING_SPEECH_FILE, "r", encoding="utf-8") as f:
                    queue = json.load(f)
            except Exception:
                queue = []
        queue.append(entry)
        try:
            with open(PENDING_SPEECH_FILE, "w", encoding="utf-8") as f:
                json.dump(queue, f, indent=2)
        except Exception as e:
            print(f"[PENDING QUEUE] Error saving {PENDING_SPEECH_FILE}: {e}")
    return entry_id

def mark_speech_transcribed(entry_id: str):
    """Removes pending speech entry once transcription successfully finishes."""
    with state.file_lock:
        if not os.path.exists(PENDING_SPEECH_FILE):
            return
        try:
            with open(PENDING_SPEECH_FILE, "r", encoding="utf-8") as f:
                queue = json.load(f)
            updated = [item for item in queue if item.get("id") != entry_id]
            with open(PENDING_SPEECH_FILE, "w", encoding="utf-8") as f:
                json.dump(updated, f, indent=2)
        except Exception as e:
            print(f"[PENDING QUEUE] Error updating {PENDING_SPEECH_FILE}: {e}")

def get_pending_speech_count() -> int:
    """Returns number of audio clips waiting to be transcribed."""
    with state.file_lock:
        if not os.path.exists(PENDING_SPEECH_FILE):
            return 0
        try:
            with open(PENDING_SPEECH_FILE, "r", encoding="utf-8") as f:
                queue = json.load(f)
            return len(queue)
        except Exception:
            return 0

def process_pending_audio_backlog() -> int:
    """
    Transcribes audio that hasn't been transcribed due to force shutdown,
    error, or internet outage.
    """
    with state.file_lock:
        if not os.path.exists(PENDING_SPEECH_FILE):
            return 0
        try:
            with open(PENDING_SPEECH_FILE, "r", encoding="utf-8") as f:
                queue = json.load(f)
        except Exception:
            return 0

    if not queue:
        return 0

    print(f"[PENDING STT] Found {len(queue)} untranscribed audio clips in queue. Transcribing...")
    processed_count = 0
    remaining = []

    for item in queue:
        clip_path = item.get("clip_path")
        if not clip_path or not os.path.exists(clip_path):
            print(f"[PENDING STT] Clip file missing on disk ({clip_path}), discarding.")
            continue

        try:
            with wave.open(clip_path, "rb") as wf:
                sample_rate = wf.getframerate()
                frames = wf.readframes(wf.getnframes())
            if sr is not None:
                audio_data = sr.AudioData(frames, sample_rate, 2)
            else:
                class RawAudioWrapper:
                    def __init__(self, raw_bytes, rate, width):
                        self._data = raw_bytes
                        self.sample_rate = rate
                        self.sample_width = width
                    def get_raw_data(self):
                        return self._data
                audio_data = RawAudioWrapper(frames, sample_rate, 2)
            text = transcribe_audio_samples(audio_data)

            if text and len(text.strip()) >= 2:
                clean_text = text.strip()
                speaker = item.get("speaker", "Unknown speaker")
                tone = item.get("tone", "neutral")
                record_microphone_event(speaker, clean_text, clip_path, tone, False, room=item.get("room"))
                processed_count += 1
                print(f"[PENDING STT SUCCESS] Transcribed clip '{clip_path}': \"{clean_text}\"")
            else:
                item["retry_count"] = item.get("retry_count", 0) + 1
                if item["retry_count"] < 3:
                    remaining.append(item)
        except Exception as e:
            print(f"[PENDING STT ERROR] Failed to process {clip_path}: {e}")
            item["retry_count"] = item.get("retry_count", 0) + 1
            if item["retry_count"] < 3:
                remaining.append(item)

    with state.file_lock:
        try:
            with open(PENDING_SPEECH_FILE, "w", encoding="utf-8") as f:
                json.dump(remaining, f, indent=2)
        except Exception as e:
            print(f"[PENDING QUEUE] Error saving remaining queue: {e}")

    return processed_count

# ==============================================================================
# BLOCK 6: ACOUSTIC BIOMETRICS & DRASTIC VOICE CHANGE DETECTION
# ==============================================================================

def extract_acoustic_features(audio_samples: Any, sample_rate: int = 16000) -> Dict[str, float]:
    """
    Extracts acoustic voice biometric features:
    - RMS Energy: Overall signal strength
    - Zero Crossing Rate: Frequency density
    - Spectral Centroid: Perceptual brightness / tone
    - Estimated Pitch (F0): Fundamental frequency via autocorrelation
    """
    if np is None or len(audio_samples) < 100:
        return {"rms": 0.0, "zcr": 0.0, "spectral_centroid": 0.0, "pitch_hz": 0.0}

    samples = audio_samples.astype(np.float32) / 32768.0
    rms = float(np.sqrt(np.mean(np.square(samples))))
    zcr = float(np.mean(np.abs(np.diff(np.signbit(samples)))))

    # Spectral centroid calculation
    fft_vals = np.abs(np.fft.rfft(samples))
    freqs = np.fft.rfftfreq(len(samples), 1.0 / sample_rate)
    sum_fft = np.sum(fft_vals)
    centroid = float(np.sum(freqs * fft_vals) / sum_fft) if sum_fft > 0 else 0.0

    # Fundamental pitch estimation via autocorrelation
    min_lag = int(sample_rate / 450)  # ~450 Hz upper voice bound
    max_lag = int(sample_rate / 65)   # ~65 Hz lower voice bound
    corr = np.correlate(samples, samples, mode='full')
    corr = corr[len(corr)//2:]
    pitch_hz = 0.0
    if len(corr) > max_lag:
        search_region = corr[min_lag:max_lag]
        if len(search_region) > 0 and np.max(search_region) > 0.12:
            peak_lag = min_lag + np.argmax(search_region)
            if peak_lag > 0:
                pitch_hz = float(sample_rate / peak_lag)

    return {
        "rms": round(rms, 4),
        "zcr": round(zcr, 4),
        "spectral_centroid": round(centroid, 1),
        "pitch_hz": round(pitch_hz, 1)
    }

def detect_drastic_voice_change(speaker: str, features: Dict[str, float]) -> Tuple[bool, str]:
    """
    Distinguishes when a voice has changed drastically on the microphone to verify
    whether the speaker username has changed or someone else grabbed the mic.
    Ensures verbatim recordings and user profiles remain accurate.
    """
    if not speaker or speaker.lower() in {"unknown speaker", "unknown"}:
        return False, "Unknown speaker"

    user_key = speaker.lower().strip()
    with state.lock:
        profile = state.speaker_acoustic_profiles.get(user_key)
        if not profile or profile.get("sample_count", 0) < 2:
            state.speaker_acoustic_profiles[user_key] = {
                "avg_pitch": features["pitch_hz"],
                "avg_centroid": features["spectral_centroid"],
                "avg_zcr": features["zcr"],
                "sample_count": 1
            }
            return False, "Initial profile established"

        avg_pitch = profile["avg_pitch"]
        avg_centroid = profile["avg_centroid"]
        new_pitch = features["pitch_hz"]
        new_centroid = features["spectral_centroid"]

        # If both current and historical pitch readings are voiced (> 75 Hz)
        if new_pitch > 75 and avg_pitch > 75:
            pitch_diff = abs(new_pitch - avg_pitch)
            centroid_ratio = new_centroid / (avg_centroid + 1e-5)

            # Drastic voice change threshold: > 60Hz pitch variance and significant spectral centroid shift
            if pitch_diff > 60 and (centroid_ratio < 0.60 or centroid_ratio > 1.45):
                warning_msg = (
                    f"Drastic voice shift detected for '{speaker}': "
                    f"Pitch={new_pitch}Hz (baseline {avg_pitch}Hz), "
                    f"Centroid={new_centroid}Hz (baseline {avg_centroid}Hz). "
                    f"Microphone username may have changed!"
                )
                print(f"[VOICE ANOMALY] {warning_msg}")
                return True, warning_msg

        # Smooth updating moving average if consistent
        alpha = 0.2
        profile["avg_pitch"] = round(avg_pitch * (1 - alpha) + new_pitch * alpha, 1)
        profile["avg_centroid"] = round(avg_centroid * (1 - alpha) + new_centroid * alpha, 1)
        profile["sample_count"] += 1

    return False, "Consistent voice"

# ==============================================================================
# BLOCK 7: AUDIO SUBSYSTEM & 7-SECOND CHUNK ENGINE
# ==============================================================================

whisper_model = None

def resolve_audio_input_device(target_name: str = AUDIO_INPUT_DEVICE) -> Tuple[Optional[int], str, int, int]:
    """Scans sounddevice for the best matching input device."""
    if sd is None:
        print("[AUDIO INIT] sounddevice is not available. Audio capture disabled.")
        return None, "sounddevice_unavailable", 16000, 1

    try:
        devices = sd.query_devices()
        input_devices = []
        for idx, dev in enumerate(devices):
            if dev.get('max_input_channels', 0) > 0:
                input_devices.append((idx, dev))

        if not input_devices:
            print("[AUDIO WARN] No audio input devices found on system!")
            return None, "No input devices", 16000, 1

        target_lower = target_name.lower().strip()
        matched_idx = None
        search_terms = [target_lower, "cable output", "vb-audio virtual cable", "vb-audio", "virtual cable", "cable"]
        for term in search_terms:
            for idx, dev in input_devices:
                if term in dev.get('name', '').lower():
                    matched_idx = idx
                    break
            if matched_idx is not None:
                break

        if matched_idx is None:
            default_dev = sd.default.device[0]
            if default_dev is not None and 0 <= default_dev < len(devices):
                matched_idx = default_dev
            else:
                matched_idx = input_devices[0][0]

        dev = devices[matched_idx]
        name = dev.get('name', f"Device #{matched_idx}")
        native_rate = int(dev.get('default_samplerate', 44100))
        return matched_idx, name, native_rate, 1

    except Exception as e:
        print(f"[AUDIO ERROR] Failed during audio device query: {e}")
        return None, "Default", 16000, 1

def resample_to_16k(audio_chunk: Any, orig_rate: int) -> Any:
    """Resamples mono or multi-channel int16 audio array to 16000Hz mono int16."""
    if np is None:
        return audio_chunk
    if orig_rate == 16000:
        if audio_chunk.ndim > 1:
            return audio_chunk[:, 0]
        return audio_chunk

    if audio_chunk.ndim > 1:
        mono = np.mean(audio_chunk, axis=1)
    else:
        mono = audio_chunk

    target_length = int(len(mono) * 16000 / orig_rate)
    resampled = np.interp(
        np.linspace(0, len(mono), target_length, endpoint=False),
        np.arange(len(mono)),
        mono
    )
    return resampled.astype(np.int16)

def get_whisper_model():
    global whisper_model
    if whisper_model is None and WhisperModel is not None:
        try:
            print(f"[VOICE] Loading Faster-Whisper ({WHISPER_MODEL_SIZE})...")
            whisper_model = WhisperModel(WHISPER_MODEL_SIZE, device="cpu", compute_type="int8")
        except Exception as e:
            print(f"[VOICE] Error initializing Whisper: {e}")
    return whisper_model

def save_7sec_audio_clip(recording: Any, sample_rate: int, channels: int) -> str:
    """Saves a 7-second audio clip to disk as a WAV file."""
    os.makedirs(AUDIO_CLIPS_DIR, exist_ok=True)
    filename = datetime.now().strftime("%Y%m%dT%H%M%S_%f") + ".wav"
    filepath = os.path.join(AUDIO_CLIPS_DIR, filename)
    with wave.open(filepath, "wb") as wf:
        wf.setnchannels(channels)
        wf.setsampwidth(2)
        wf.setframerate(sample_rate)
        wf.writeframes(recording.tobytes())
    return filepath

def file_audio_chunk_for_speaker(clip_path: str, speaker: str, recording_16k: Any = None, text: str = "") -> str:
    """
    Files 7-second audio clips and transcription records into the dedicated user folder:
      audio_memory/usernames/<speaker>/clip_<timestamp>.wav
      audio_memory/usernames/<speaker>/transcripts.jsonl
    Ensures recordings are accurately cataloged for every user who speaks on the microphone.
    """
    clean_spk = re.sub(r'[^a-zA-Z0-9_\-\$]', '', speaker).strip()
    if not clean_spk:
        clean_spk = "unidentified_speaker"

    user_folder = os.path.join(AUDIO_USERS_DIR, clean_spk)
    os.makedirs(user_folder, exist_ok=True)

    base_name = os.path.basename(clip_path) if clip_path else f"clip_{datetime.now().strftime('%Y%m%dT%H%M%S_%f')}.wav"
    user_file_path = os.path.join(user_folder, base_name)

    try:
        if clip_path and os.path.exists(clip_path) and clip_path != user_file_path:
            shutil.copy2(clip_path, user_file_path)
        elif recording_16k is not None:
            with wave.open(user_file_path, "wb") as wf:
                wf.setnchannels(1)
                wf.setsampwidth(2)
                wf.setframerate(16000)
                wf.writeframes(recording_16k.tobytes())
        print(f"[AUDIO FILED] Saved mic clip for '{clean_spk}': {user_file_path}")
    except Exception as e:
        print(f"[AUDIO FILING ERROR] Could not save to {user_file_path}: {e}")

    # Append to user's transcript ledger
    if text:
        try:
            with open(os.path.join(user_folder, "transcripts.jsonl"), "a", encoding="utf-8") as f:
                f.write(json.dumps({
                    "timestamp": format_bot_timestamp(),
                    "text": text,
                    "clip": os.path.basename(user_file_path)
                }) + "\n")
        except Exception:
            pass

    return user_file_path

def detect_audio_tone(audio_samples: Any) -> str:
    """Estimates audio tone from sample properties."""
    if np is None or len(audio_samples) == 0:
        return "unknown"
    samples = audio_samples.astype(np.float32) / 32768.0
    rms = float(np.sqrt(np.mean(np.square(samples))))
    peak = float(np.max(np.abs(samples)))
    crossings = float(np.mean(np.abs(np.diff(np.signbit(samples)))))
    if rms < 0.003:
        return "silent or unclear"
    if peak > 0.95 or rms > 0.25:
        return "agitated or emphatic"
    if crossings > 0.18 and rms > 0.03:
        return "energetic"
    if rms < 0.02:
        return "calm or quiet"
    return "neutral"

def transcribe_audio_samples(audio_data: Any) -> Optional[str]:
    """Transcribes audio using local Whisper or Google speech recognition fallback."""
    model = get_whisper_model()
    if model is not None and np is not None:
        try:
            samples = np.frombuffer(audio_data.get_raw_data(), dtype=np.int16).astype(np.float32) / 32768.0
            # Conversational prompt trains Whisper to recognize casual chat, informal words, and room speech
            prompt = "Conversational chat room dialogue, informal slang, casual speech: KaeKae, Camfrog, room mic, talking, chilling."
            segments, _ = model.transcribe(
                samples,
                language="en",
                beam_size=5,
                temperature=[0.0, 0.2],
                initial_prompt=prompt,
                condition_on_previous_text=False,
                vad_filter=True,
                vad_parameters=dict(min_silence_duration_ms=350, speech_pad_ms=300)
            )
            text = " ".join(seg.text.strip() for seg in segments).strip()
            if not text:
                segments, _ = model.transcribe(
                    samples,
                    language="en",
                    beam_size=3,
                    initial_prompt=prompt,
                    condition_on_previous_text=False,
                    vad_filter=False
                )
                text = " ".join(seg.text.strip() for seg in segments).strip()
            if text:
                return text
        except Exception as e:
            print(f"[WHISPER] Faster-Whisper error: {e}")

    # Fallback to Google SR
    try:
        r = sr.Recognizer()
        text = r.recognize_google(audio_data)
        if text:
            return text
    except sr.UnknownValueError:
        pass
    except Exception as e:
        print(f"[GOOGLE SR] Fallback recognition error: {e}")

    return None

def record_microphone_event(speaker: str, text: str, clip_path: Optional[str], tone: str, talk_button_active: bool, room: Optional[str] = None):
    """Logs microphone transcripts to disk, memory, and user profiles with standardized timestamp."""
    ts_str = format_bot_timestamp()
    entry = {
        "username": speaker,
        "timestamp": ts_str,
        "message": text,
        "source": "microphone",
        "clip": clip_path,
        "tone": tone,
        "talk_active": talk_button_active,
        "room": room or state.current_focused_room
    }
    with state.lock:
        state.recent_mic_transcripts.append(entry)
        if len(state.recent_mic_transcripts) > 500:
            state.recent_mic_transcripts.pop(0)

        if speaker.lower() not in {"unknown speaker", "unknown", BOT_USERNAME.lower()}:
            user_key = next((k for k in state.users if k.lower() == speaker.lower()), speaker)
            if user_key in state.users:
                profile = state.users[user_key]
                profile.setdefault("microphone_transcripts", []).append({
                    "timestamp": ts_str,
                    "message": text,
                    "tone": tone
                })
                if len(profile["microphone_transcripts"]) > MAX_PROFILE_ITEMS:
                    profile["microphone_transcripts"].pop(0)

    with state.file_lock:
        try:
            with open(AUDIO_TRANSCRIPTS_FILE, "a", encoding="utf-8") as f:
                json.dump(entry, f)
                f.write("\n")
        except Exception as e:
            print(f"[STORAGE] Error saving mic transcript: {e}")

def get_five_minute_bucket_str(dt: Optional[datetime] = None) -> str:
    """Calculates 5-minute timespan window label (e.g. 09/24 14:05-14:10)."""
    if dt is None:
        dt = datetime.now()
    min_start = (dt.minute // 5) * 5
    min_end = min_start + 5
    return f"{dt.strftime('%m/%d %H:')}{min_start:02d}-{min_end:02d}"

def record_mic_grab_chunk(speaker: str, chunk_duration: float = 7.0):
    """
    Records and logs how many times each person grabs the microphone and for how long
    they have been on the microphone, broken down into 5-minute timespans.
    """
    if (not speaker or 
        speaker.lower() in {"unknown speaker", "unknown", BOT_USERNAME.lower()} or 
        speaker.lower() in IGNORED_USERS or 
        speaker.lower() in BOT_ALT_USERNAMES or 
        not is_valid_camfrog_username(speaker)):
        return

    now_t = time.time()
    dt = datetime.now()
    bucket = get_five_minute_bucket_str(dt)
    ts_str = format_bot_timestamp(dt)

    with state.lock:
        state.current_room_users.add(speaker)
        state.room_users_activity[speaker.lower()] = now_t

        curr_session = state.current_active_grab_session
        if curr_session and curr_session["speaker"].lower() == speaker.lower() and (now_t - state.last_mic_chunk_time < 12.0):
            curr_session["duration"] += chunk_duration
            curr_session["end_time"] = now_t
            curr_session["chunks"] = curr_session.get("chunks", 1) + 1
        else:
            if curr_session:
                state.mic_grab_sessions.append(curr_session)
                if len(state.mic_grab_sessions) > 2000:
                    state.mic_grab_sessions.pop(0)

            state.current_active_grab_session = {
                "speaker": speaker,
                "start_time": now_t,
                "end_time": now_t + chunk_duration,
                "duration": chunk_duration,
                "chunks": 1,
                "timestamp": ts_str,
                "five_min_bucket": bucket,
                "room": state.current_focused_room
            }

        state.last_mic_chunk_time = now_t

    with state.file_lock:
        try:
            with open(MIC_GRABS_FILE, "a", encoding="utf-8") as f:
                json.dump({
                    "speaker": speaker,
                    "timestamp": ts_str,
                    "duration": chunk_duration,
                    "five_min_bucket": bucket,
                    "room": state.current_focused_room
                }, f)
                f.write("\n")
        except Exception:
            pass

def get_random_wake_response() -> str:
    """Selects a wake response at random, guaranteeing no back-to-back repetitions."""
    with state.lock:
        available = [r for r in VOICE_WAKE_RESPONSES if r != state.last_voice_wake_reply]
        if not available:
            available = VOICE_WAKE_RESPONSES
        chosen = random.choice(available)
        state.last_voice_wake_reply = chosen
        return chosen

def deduplicate_overlap_text(new_text: str, prev_text: str) -> str:
    """Removes overlapping prefix words caused by audio chunk overlap window."""
    if not prev_text or not new_text:
        return new_text
    
    clean_prev = prev_text.strip().lower()
    clean_new = new_text.strip().lower()
    
    # If identical or already covered
    if clean_new == clean_prev or clean_new in clean_prev:
        return ""
    
    prev_words = [re.sub(r'[^\w]', '', w) for w in clean_prev.split() if re.sub(r'[^\w]', '', w)]
    orig_new_words = new_text.strip().split()
    new_words = [re.sub(r'[^\w]', '', w.lower()) for w in orig_new_words if re.sub(r'[^\w]', '', w)]
    
    if not prev_words or not new_words:
        return new_text.strip()
        
    # Check for prefix overlap of between 2 and 8 words
    max_check = min(len(prev_words), len(new_words), 8)
    for n in range(max_check, 1, -1):
        if new_words[:n] == prev_words[-n:]:
            trimmed = " ".join(orig_new_words[n:])
            return trimmed.strip()
            
    return new_text.strip()

audio_chunk_queue = queue.Queue(maxsize=15)

def audio_transcription_worker():
    """Processes queued audio chunks asynchronously with overlap deduplication."""
    last_transcribed_text = ""
    last_speaker = ""

    while not state.shutdown_event.is_set():
        try:
            item = audio_chunk_queue.get(timeout=0.5)
        except queue.Empty:
            continue

        recording_16k, peak, timestamp = item

        try:
            # Save clip file immediately to disk
            clip_path = save_7sec_audio_clip(recording_16k, 16000, 1)

            # Detect current active speaker on mic and room using CEF Fast-path probe if available
            speaker = None
            if global_probe is not None:
                probe_speaker = global_probe.get_speaker()
                if (probe_speaker and probe_speaker != "Unknown speaker" and 
                    is_valid_camfrog_username(probe_speaker) and 
                    probe_speaker.lower() not in IGNORED_USERS and 
                    probe_speaker.lower() not in BOT_ALT_USERNAMES):
                    speaker = probe_speaker

            if not speaker or not is_valid_camfrog_username(speaker) or speaker.lower() in IGNORED_USERS or speaker.lower() in BOT_ALT_USERNAMES:
                win = get_camfrog_window()
                speaker = find_active_speaker(win) if win else "Unknown speaker"
                if not is_valid_camfrog_username(speaker) or speaker.lower() in IGNORED_USERS or speaker.lower() in BOT_ALT_USERNAMES:
                    speaker = "Unknown speaker"

            with state.lock:
                state.current_active_speaker = speaker
                curr_room = state.current_focused_room

            if speaker != "Unknown speaker":
                record_mic_grab_chunk(speaker, chunk_duration=7.0)

            # Extract acoustic features & check for drastic voice shift first
            acoustic_feats = extract_acoustic_features(recording_16k, 16000)
            tone = detect_audio_tone(recording_16k)
            is_anomaly, anomaly_msg = detect_drastic_voice_change(speaker, acoustic_feats)

            # File clip under speaker's dedicated directory immediately via async filer or fallback
            if global_audio_filer is not None:
                global_audio_filer.enqueue_chunk(
                    audio_data=recording_16k.tobytes(),
                    speaker=speaker,
                    sample_rate=16000,
                    peak=peak,
                    tone=tone
                )
            else:
                file_audio_chunk_for_speaker(clip_path, speaker, recording_16k)

            # Persist to pending speech queue BEFORE transcribing so it cannot be lost
            entry_id = enqueue_pending_speech(clip_path, speaker, curr_room, peak, tone, acoustic_feats)

            # Transcribe
            if sr is not None:
                audio_data = sr.AudioData(recording_16k.tobytes(), 16000, 2)
            else:
                class RawAudioWrapper:
                    def __init__(self, raw_bytes, rate, width):
                        self._data = raw_bytes
                        self.sample_rate = rate
                        self.sample_width = width
                    def get_raw_data(self):
                        return self._data
                audio_data = RawAudioWrapper(recording_16k.tobytes(), 16000, 2)
            detected_text = transcribe_audio_samples(audio_data)

            if not detected_text or len(detected_text.strip()) < 2:
                # Kept in pending speech queue for catchup if it was speech, or cleaned up if verified noise
                continue

            raw_clean_text = detected_text.strip()

            # Overlap deduplication: trim duplicate words if continuation of previous utterance
            if speaker == last_speaker:
                clean_text = deduplicate_overlap_text(raw_clean_text, last_transcribed_text)
            else:
                clean_text = raw_clean_text

            if not clean_text or len(clean_text.strip()) < 2:
                continue

            last_transcribed_text = raw_clean_text
            last_speaker = speaker

            print(f"[MIC HEARD] \"{clean_text}\" (Speaker: {speaker}, Peak: {peak}, Overlap: {OVERLAP_SECONDS}s)")

            # Remove from pending queue since transcription succeeded
            mark_speech_transcribed(entry_id)

            # Record event in archives & memory, and log mic grab session (5-min increments)
            record_microphone_event(speaker, clean_text, clip_path, tone, True, room=curr_room)
            record_mic_grab_chunk(speaker, 7.0)

            lower_text = clean_text.lower()

            # 1. Audio-Triggered Moderation Queries (Any user speaking on microphone)
            mod_audio_queries = [
                ("who unblocked", "unblocked"),
                ("who blocked", "blocked"),
                ("who unpunished", "unpunished"),
                ("who punished", "punished"),
                ("who unbanned", "unbanned"),
                ("who banned", "banned"),
                ("who kicked", "kicked"),
            ]
            audio_mod_handled = False
            for trig, act in mod_audio_queries:
                if trig in lower_text:
                    parts = re.split(rf'{trig}', clean_text, flags=re.IGNORECASE)
                    target = parts[-1].strip() if len(parts) > 1 else ""
                    print(f"[MIC MOD QUERY] Speaker '{speaker}' asked on mic: '{trig}' for '{target}'")
                    handle_moderation_query(speaker, act, target)
                    audio_mod_handled = True
                    break
            if audio_mod_handled:
                continue

            # 2. Audio-Triggered User Intelligence: "who is" or "info on" (Any user on microphone)
            if "who is" in lower_text:
                target = re.split(r'who\s+is\s+', clean_text, flags=re.IGNORECASE)[-1].strip()
                print(f"[MIC BIO QUERY] Speaker '{speaker}' asked on mic who is: '{target}'")
                handle_user_lookup(speaker, target, lookup_type="bio")
                continue

            if "info on" in lower_text or lower_text.startswith("info ") or lower_text.startswith("!info "):
                target = re.split(r'info\s+(?:on\s+)?', clean_text, flags=re.IGNORECASE)[-1].strip()
                print(f"[MIC STATS QUERY] Speaker '{speaker}' asked on mic info on: '{target}'")
                handle_user_lookup(speaker, target, lookup_type="stats")
                continue

            # 3. Audio-Triggered IDK: "idk" anywhere in speech
            if re.search(r'\b(!?idk)\b', lower_text):
                print(f"[MIC IDK QUERY] Speaker '{speaker}' said idk on mic: '{clean_text}'")
                handle_idk_command(speaker, clean_text)
                continue

            # 4. Check Voice Wake Triggers ("kae", "kaekae", "kaebot")
            if any(trig in lower_text for trig in VOICE_WAKE_TRIGGERS):
                wake_reply = get_random_wake_response()
                print(f"[MIC WAKE TRIGGER] Detected wake word in '{clean_text}' -> Replying: '{wake_reply}'")
                send_chat_message(wake_reply, override_mute=True)
                continue

            # If Transcribe is ON or Repeat Mode is ON, echo speech to Camfrog chat
            with state.lock:
                transcribe_on = state.transcribe_enabled
                repeat_on = state.repeat_mode

            if transcribe_on or repeat_on:
                safe_spk = speaker if (speaker and is_valid_camfrog_username(speaker)) else "Unknown speaker"
                ts_formatted = format_bot_timestamp()
                chat_transcript = f"[MIC] {safe_spk} {ts_formatted}: {clean_text}"
                print(f"[TRANSCRIBE POST] Broadcasting to chat: {chat_transcript}")
                send_chat_message(chat_transcript[:MAX_MSG_LENGTH], override_mute=True)

        except Exception as e:
            print(f"[AUDIO WORKER ERROR] Exception processing chunk: {e}")
            traceback.print_exc()

def voice_listener_worker():
    """Continuously streams audio from VB-Audio Virtual Cable with sliding overlap buffer so no speech is missed."""
    if sd is None or np is None:
        print("[AUDIO THREAD] sounddevice or numpy missing; microphone capture is disabled.")
        return

    dev_idx, dev_name, native_rate, channels = resolve_audio_input_device(AUDIO_INPUT_DEVICE)
    with state.lock:
        state.audio_device_index = dev_idx
        state.audio_device_name = dev_name
        state.audio_native_rate = native_rate

    use_rate = 16000
    try:
        sd.check_input_settings(device=dev_idx, samplerate=16000, channels=channels, dtype="int16")
    except Exception:
        use_rate = native_rate

    print(f"[AUDIO THREAD] Started continuous stream on '{dev_name}' (device #{dev_idx}) at {use_rate}Hz with {OVERLAP_SECONDS}s sliding overlap.")

    # Start the async transcription worker
    worker_thread = threading.Thread(target=audio_transcription_worker, daemon=True)
    worker_thread.start()

    # Process any backlogged pending speech on startup
    backlog_count = process_pending_audio_backlog()
    if backlog_count > 0:
        print(f"[AUDIO THREAD] Caught up {backlog_count} pending audio clips from prior session.")

    step_seconds = max(1.0, CHUNK_SECONDS - OVERLAP_SECONDS)
    step_frames = int(step_seconds * use_rate)
    overlap_samples = int(OVERLAP_SECONDS * 16000)
    prev_overlap_tail = np.zeros(overlap_samples, dtype=np.int16)

    print(f"[AUDIO THREAD] Audio engine active: {step_seconds}s steps with {OVERLAP_SECONDS}s glued overlap into Faster-Whisper.")

    while not state.shutdown_event.is_set():
        with state.lock:
            if not state.listening_enabled:
                time.sleep(0.3)
                continue
            silence_threshold = state.audio_silence_threshold
            gain_multiplier = state.audio_gain

        try:
            # High-reliability PortAudio recording for step_seconds (5.0s)
            raw_rec = sd.rec(
                frames=step_frames,
                samplerate=use_rate,
                channels=channels,
                dtype="int16",
                device=dev_idx
            )
            sd.wait()

            with state.lock:
                if not state.listening_enabled:
                    continue

            # Resample chunk to 16kHz mono
            if use_rate != 16000 or raw_rec.ndim > 1:
                fresh_16k = resample_to_16k(raw_rec, use_rate)
            else:
                fresh_16k = raw_rec.flatten()

            # Digital gain
            if gain_multiplier != 1.0:
                amplified = fresh_16k.astype(np.float32) * gain_multiplier
                fresh_16k = np.clip(amplified, -32768, 32767).astype(np.int16)

            # Local DSP Clean-up: Strip 85Hz AC rumble, DC offset, and apply adaptive noise gate
            if dsp_cleaner is not None:
                try:
                    fresh_16k, dsp_stats = dsp_cleaner.clean_chunk(fresh_16k)
                except Exception as e_dsp:
                    pass

            peak = int(np.max(np.abs(fresh_16k))) if len(fresh_16k) > 0 else 0
            with state.lock:
                state.audio_last_peak = peak
                state.audio_last_capture_time = time.time()

            # Form full 7-second chunk with glued 2-second overlap context
            full_7s_chunk = np.concatenate([prev_overlap_tail, fresh_16k])

            # Retain last 2 seconds for next iteration
            if len(fresh_16k) >= overlap_samples:
                prev_overlap_tail = fresh_16k[-overlap_samples:].copy()
            else:
                prev_overlap_tail = full_7s_chunk[-overlap_samples:].copy()

            # Live peak visual indicator
            bars = "#" * min(25, int(peak / 600)) if peak > 0 else ""
            status_indicator = "SPEAKING" if peak >= silence_threshold else "silence"
            print(f"[AUDIO] Level: {peak:5d} [{bars:<25}] ({status_indicator})")

            win_peak = int(np.max(np.abs(full_7s_chunk)))
            if peak >= silence_threshold or win_peak >= silence_threshold:
                try:
                    audio_chunk_queue.put_nowait((full_7s_chunk, win_peak, time.time()))
                except queue.Full:
                    pass

        except Exception as e:
            print(f"[AUDIO THREAD] Recording cycle error: {e}")
            traceback.print_exc()
            time.sleep(1.0)

# Backward-compatibility alias for multi-terminal workers
audio_recorder_loop = voice_listener_worker

def stop_transcription_action(source: str = "hotkey"):
    """
    Instantly disables live microphone transcription, clears pending Whisper queue,
    and updates bot_state.json across all terminals.
    """
    with state.lock:
        state.transcribe_enabled = False
        while not audio_chunk_queue.empty():
            try:
                audio_chunk_queue.get_nowait()
            except Exception:
                break
    save_bot_runtime_state()
    print(f"\n[HOTKEY] >>> STOP TRANSCRIBE TRIGGERED ({source}) <<< Live microphone transcription disabled.")
    try:
        send_chat_message(f"{format_bot_timestamp()} Live transcription has been stopped.", override_mute=True)
    except Exception:
        pass

def start_transcribe_hotkey_listener():
    """
    Background hook that monitors:
    1. Left Ctrl + Right Mouse Click -> Instantly stops transcribing
    2. F8 -> Toggles transcription ON/OFF
    3. a+s+d+f -> Toggles room listening
    """
    def _listener_thread():
        # First register keyboard hotkeys if keyboard module is present
        try:
            import keyboard
            def _f8_toggle():
                with state.lock:
                    state.transcribe_enabled = not state.transcribe_enabled
                    cur = state.transcribe_enabled
                    if not cur:
                        while not audio_chunk_queue.empty():
                            try:
                                audio_chunk_queue.get_nowait()
                            except Exception:
                                break
                save_bot_runtime_state()
                print(f"[HOTKEY] F8: Live transcription toggled {'ON' if cur else 'OFF'}")
                try:
                    send_chat_message(f"{format_bot_timestamp()} Live transcription is {'ON' if cur else 'OFF'}.", override_mute=True)
                except Exception:
                    pass

            def _asdf_toggle():
                with state.lock:
                    state.listening_enabled = not state.listening_enabled
                    cur = state.listening_enabled
                save_bot_runtime_state()
                print(f"[HOTKEY] ASDF: Listening toggled {'ON' if cur else 'OFF'}")
                try:
                    send_chat_message(f"{format_bot_timestamp()} Listening toggled {'ON' if cur else 'OFF'}.", override_mute=True)
                except Exception:
                    pass

            keyboard.add_hotkey("f8", _f8_toggle, trigger_on_release=True)
            keyboard.add_hotkey("a+s+d+f", _asdf_toggle, trigger_on_release=True)
            print("[HOTKEY] Keyboard hotkeys initialized (F8 = Transcribe Toggle, ASDF = Listen Toggle).")
        except Exception as e:
            print(f"[HOTKEY] Keyboard hotkey registration notice: {e}")

        # Windows Global Mouse Hook for Left-Ctrl + Right-Click
        if sys.platform == "win32":
            try:
                import ctypes
                user32 = ctypes.windll.user32
                VK_LCONTROL = 0xA2
                VK_RBUTTON = 0x02

                print("[HOTKEY] Active: Left-Ctrl + Right-Click is armed to stop transcription.")
                was_rclick_down = False

                while not state.shutdown_event.is_set():
                    # High bit of GetAsyncKeyState indicates key/button is currently down
                    lctrl_down = bool(user32.GetAsyncKeyState(VK_LCONTROL) & 0x8000)
                    rbutton_down = bool(user32.GetAsyncKeyState(VK_RBUTTON) & 0x8000)

                    if lctrl_down and rbutton_down:
                        if not was_rclick_down:
                            was_rclick_down = True
                            stop_transcription_action(source="Left-Ctrl + Right-Click")
                    elif not rbutton_down:
                        was_rclick_down = False

                    time.sleep(0.04)
            except Exception as e:
                print(f"[HOTKEY] Windows mouse hook error: {e}")
        else:
            while not state.shutdown_event.is_set():
                time.sleep(1.0)

    t = threading.Thread(target=_listener_thread, daemon=True)
    t.start()
    return t

# ==============================================================================
# BLOCK 8: CAMFROG UI & WINDOW CONTROLLER (OCR, TALK BUTTON, CHAT SENDER)
# ==============================================================================

camfrog_app = None
camfrog_win = None

def get_camfrog_window():
    global camfrog_app, camfrog_win
    if camfrog_win is not None:
        try:
            if camfrog_win.exists():
                r = camfrog_win.rectangle()
                if r.width() >= 400 and r.height() >= 300:
                    return camfrog_win
        except Exception:
            pass

    # Find the largest visible window belonging to Camfrog (the room window)
    best_hwnd = None
    best_area = 0
    best_title = ""

    def enum_cb(hwnd, _):
        nonlocal best_hwnd, best_area, best_title
        if not win32gui.IsWindowVisible(hwnd):
            return
        title = win32gui.GetWindowText(hwnd).strip()
        if not title:
            return
        
        # Check process name or title keywords
        try:
            _, pid = win32process.GetWindowThreadProcessId(hwnd)
            h_proc = win32api.OpenProcess(win32con.PROCESS_QUERY_INFORMATION | win32con.PROCESS_VM_READ, False, pid)
            proc_path = win32process.GetModuleFileNameEx(h_proc, 0)
            win32api.CloseHandle(h_proc)
            if "camfrog" not in proc_path.lower():
                return
        except Exception:
            if not any(w in title.lower() for w in ["camfrog", "lounge", "central", "pad", "room"]):
                return

        rect = win32gui.GetWindowRect(hwnd)
        w = rect[2] - rect[0]
        h = rect[3] - rect[1]
        if w >= 400 and h >= 300:
            area = w * h
            # Boost score for room windows over contact list
            score = area
            if title.lower() not in {"camfrog", "camfrog video chat"}:
                score += 10000000
            if score > best_area:
                best_area = score
                best_hwnd = hwnd
                best_title = title

    try:
        win32gui.EnumWindows(enum_cb, None)
    except Exception:
        pass

    if best_hwnd:
        try:
            camfrog_app = Application(backend="uia").connect(handle=best_hwnd)
            camfrog_win = camfrog_app.window(handle=best_hwnd)
            with state.lock:
                if state.current_focused_room != best_title:
                    state.current_focused_room = best_title
                    print(f"[ROOM FOCUS] Connected to Camfrog Room Window: '{best_title}' (HWND: {best_hwnd})")
            return camfrog_win
        except Exception as e:
            print(f"[WINDOW CONNECT NOTICE] {e}")

    # Fallback to title regex connection
    try:
        camfrog_app = Application(backend="uia").connect(
            found_index=0,
            title_re="(?i).*(Players__Lounge|DRAMA_CENTRAL|Pepe's Pad|Camfrog).*"
        )
        camfrog_win = camfrog_app.top_window()
        title = camfrog_win.window_text().strip()
        if title:
            with state.lock:
                if state.current_focused_room != title:
                    state.current_focused_room = title
                    print(f"[ROOM FOCUS] Connected to Camfrog window: '{title}'")
        return camfrog_win
    except Exception:
        return None

def load_calibrated_stage_coordinates() -> Optional[Dict[str, Any]]:
    """Loads calibrated coordinates from camfrog_coords.json or config.json if available."""
    for fname in ["camfrog_coords.json", CONFIG_FILE]:
        if os.path.exists(fname):
            try:
                with open(fname, "r", encoding="utf-8") as f:
                    data = json.load(f)
                    if "talk_button" in data or "camfrog_ui_layout" in data:
                        return data.get("camfrog_ui_layout", data)
            except Exception:
                pass
    return None

def find_active_speaker(win) -> str:
    """
    Finds the active microphone speaker's username using Chromium UIA inspection
    and OCR on the region visually to the RIGHT of the speaker icon / Talk button.
    Accurately resolves usernames like 'OMGitsMyPHONE' against active room members.
    """
    if not win:
        return "Unknown speaker"

    with state.lock:
        room_users = list(state.current_room_users)
        known_users = [u for u in room_users if is_valid_camfrog_username(u)]
        if not known_users:
            known_users = [u for u in state.users.keys() if is_valid_camfrog_username(u)]

    def _resolve_against_room_users(candidate: str) -> Optional[str]:
        if not candidate or len(candidate) < 2:
            return None
        cand_clean = re.sub(r'[^a-zA-Z0-9_\-\$]', '', candidate.split()[0] if candidate.split() else "")
        if not cand_clean or cand_clean.lower() in IGNORED_USERS or cand_clean.lower() in BOT_ALT_USERNAMES:
            return None

        # Check exact case-insensitive match first
        for u in known_users:
            if u.lower() == cand_clean.lower():
                return u

        # Check close fuzzy match (fixes OCR artifacts like '0MGitsMyPHONE' -> 'OMGitsMyPHONE')
        best_match = None
        best_ratio = 0.0
        for u in known_users:
            ratio = SequenceMatcher(None, cand_clean.lower(), u.lower()).ratio()
            if u.lower() in cand_clean.lower() or cand_clean.lower() in u.lower():
                ratio = max(ratio, 0.88)
            if ratio > best_ratio and ratio >= 0.70:
                best_ratio = ratio
                best_match = u

        if best_match and best_ratio >= 0.72:
            return best_match

        if is_valid_camfrog_username(cand_clean):
            return cand_clean
        return None

    # Step 1: UI Automation search for active talk indicators & adjacent labels
    try:
        talk_rect = None
        for ctrl in win.descendants():
            c_type = ctrl.element_info.control_type
            if c_type in {"Text", "ListItem", "Button", "Pane"}:
                txt = (ctrl.element_info.name or ctrl.window_text() or "").strip()
                if not txt:
                    continue

                low = txt.lower()
                # Direct talking banners (e.g. "Talking: OMGitsMyPHONE", "OMGitsMyPHONE is talking")
                if "talking:" in low or "speaking:" in low or "on mic:" in low:
                    m = re.search(r'(?:talking|speaking|on mic):\s*([a-zA-Z0-9_\-\$]{2,20})', txt, re.IGNORECASE)
                    if m:
                        matched = _resolve_against_room_users(m.group(1))
                        if matched:
                            with state.lock:
                                state.current_active_speaker = matched
                            return matched

                if " is talking" in low:
                    m = re.search(r'([a-zA-Z0-9_\-\$]{2,20})\s+is talking', txt, re.IGNORECASE)
                    if m:
                        matched = _resolve_against_room_users(m.group(1))
                        if matched:
                            with state.lock:
                                state.current_active_speaker = matched
                            return matched

                if c_type == "Button" and (low == "talk" or "push-to-talk" in low):
                    talk_rect = ctrl.rectangle()

        # Step 2: Controls adjacent to Talk button
        if talk_rect:
            for ctrl in win.descendants():
                if ctrl.element_info.control_type in {"Text", "Button"}:
                    rect = ctrl.rectangle()
                    if abs(rect.top - talk_rect.top) <= 35 and 0 <= (rect.left - talk_rect.right) <= 220:
                        raw = (ctrl.element_info.name or ctrl.window_text() or "").strip()
                        matched = _resolve_against_room_users(raw)
                        if matched:
                            with state.lock:
                                state.current_active_speaker = matched
                            return matched
    except Exception:
        pass

    # Step 3: Calibrated Micro-ROI OCR Fallback (situated right of speaker icon / Talk button)
    coords = load_calibrated_stage_coordinates()
    reg = None
    if coords and "active_speaker_ocr_region" in coords:
        c_reg = coords["active_speaker_ocr_region"]
        reg = (int(c_reg["left"]), int(c_reg["top"]), int(c_reg["width"]), int(c_reg["height"]))
    elif win:
        try:
            win_rect = win.rectangle()
            left = win_rect.left + int(win_rect.width() * 0.82)
            top = win_rect.top + int(win_rect.height() * 0.58)
            reg = (left, top, 190, 30)
        except Exception:
            pass

    if reg and pyautogui is not None and pytesseract is not None:
        try:
            shot = pyautogui.screenshot(region=reg)
            if Image is not None:
                w, h = shot.size
                upscaled = shot.resize((w * 3, h * 3), Image.BICUBIC if hasattr(Image, "BICUBIC") else Image.Resampling.BICUBIC)
                gray = upscaled.convert('L')
                if ImageEnhance is not None:
                    gray = ImageEnhance.Contrast(gray).enhance(2.2)
                if ImageOps is not None:
                    stat = gray.histogram()
                    avg_b = sum(i * count for i, count in enumerate(stat)) / (w * h * 9)
                    if avg_b < 125:
                        gray = ImageOps.invert(gray)
            else:
                gray = shot.convert('L')

            custom_config = r'--psm 7 -c tessedit_char_whitelist=abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789_-$.'
            txt = pytesseract.image_to_string(gray, config=custom_config).strip()
            matched = _resolve_against_room_users(txt)
            if matched:
                with state.lock:
                    if state.current_active_speaker != matched:
                        state.current_active_speaker = matched
                        print(f"[ACTIVE SPEAKER OCR] Identified mic speaker: '{matched}'")
                return matched
        except Exception:
            pass

    return "Unknown speaker"

def scan_room_users(win) -> Set[str]:
    """
    Scans the Camfrog room member list / participant area to identify who is in the room.
    Streamlines with room memory, !who, !chat, and !diss commands.
    """
    if not win:
        with state.lock:
            return set(state.current_room_users)

    detected: Set[str] = set()
    now_t = time.time()
    try:
        win_rect = win.rectangle()
        # Camfrog user list is docked on the right side
        for ctrl in win.descendants():
            c_type = ctrl.element_info.control_type
            if c_type in {"ListItem", "TreeItem", "Text"}:
                txt = (ctrl.element_info.name or ctrl.window_text() or "").strip()
                if not txt or len(txt) < 2 or len(txt) > 35:
                    continue
                clean = re.sub(r'[^a-zA-Z0-9_\-\$]', '', txt)
                if not clean or clean.lower() in IGNORED_USERS or clean.lower() in BOT_ALT_USERNAMES:
                    continue
                if any(w in clean.lower() for w in ["camfrog", "room", "talk", "operator", "admin"]):
                    continue
                rect = ctrl.rectangle()
                if rect.left >= win_rect.left + int(win_rect.width() * 0.70):
                    detected.add(clean)
                    state.room_users_activity[clean.lower()] = now_t
    except Exception:
        pass

    with state.lock:
        state.current_room_users.update(detected)
        # Prune users not seen for > 30 minutes
        expired = [u for u, t in state.room_users_activity.items() if now_t - t > 1800]
        for exp in expired:
            del state.room_users_activity[exp]
            state.current_room_users = {u for u in state.current_room_users if u.lower() != exp}
        return set(state.current_room_users)

def room_users_scanner_worker():
    """
    Continuously monitors the Camfrog user list in the background every 4-5 seconds.
    Ensures state.current_room_users has up-to-date room participant names
    (such as 'OMGitsMyPHONE') for fast, accurate speaker identification and commands.
    """
    while not state.shutdown_event.is_set():
        try:
            win = get_camfrog_window()
            if win:
                scan_room_users(win)
        except Exception:
            pass
        time.sleep(4.0)

def get_talk_button_region(win) -> Tuple[int, int, int, int]:
    """
    Locates the Talk button rectangle in the Camfrog stage controls.
    CRITICAL: The TALK button is visually to the LEFT of the push-to-talk arrow down button!
    Avoids accidentally pressing the dropdown arrow which controls hands-free/PTT menu.
    """
    coords = load_calibrated_stage_coordinates()
    if coords:
        if "talk_button_x" in coords and "talk_button_y" in coords:
            tx, ty = int(coords["talk_button_x"]), int(coords["talk_button_y"])
            return (tx - 35, ty - 15, tx + 35, ty + 15)
        if "talk_button" in coords and isinstance(coords["talk_button"], dict) and "x" in coords["talk_button"]:
            tx, ty = int(coords["talk_button"]["x"]), int(coords["talk_button"]["y"])
            return (tx - 35, ty - 15, tx + 35, ty + 15)

    if win:
        try:
            # Look for talk button or dropdown arrow among descendants
            arrow_rect = None
            talk_rect = None
            for ctrl in win.descendants():
                if ctrl.element_info.control_type == "Button":
                    name = (ctrl.element_info.name or "").strip().lower()
                    rect = ctrl.rectangle()
                    if "arrow" in name or "dropdown" in name or "hands-free" in name or "push-to-talk" in name:
                        arrow_rect = rect
                    if name == "talk":
                        talk_rect = rect
                    if 1350 <= rect.left <= 1800 and 450 <= rect.top <= 750:
                        if not talk_rect:
                            talk_rect = rect

            if arrow_rect:
                # The TALK button is positioned to the LEFT of the arrow down
                offset = coords.get("talk_button_offset_left_of_arrow_px", 55) if coords else 55
                tb_center_x = arrow_rect.left - offset
                tb_center_y = (arrow_rect.top + arrow_rect.bottom) // 2
                return (tb_center_x - 30, tb_center_y - 15, tb_center_x + 30, tb_center_y + 15)

            if talk_rect:
                # If talk_rect was actually the arrow down or container, offset to left
                left = talk_rect.left
                top = talk_rect.top
                return (left - 50, top, left + 20, talk_rect.bottom)
        except Exception:
            pass

    # Default fallback window percentage
    if win:
        win_rect = win.rectangle()
        # Offset to the left of the arrow
        left = win_rect.left + int(win_rect.width() * 0.74)
        top = win_rect.top + int(win_rect.height() * 0.58)
        return (left, top, left + 80, top + 35)

    return (1450, 580, 1530, 615)

def check_talk_button_state_fast(win) -> Tuple[bool, str, Tuple[int, int]]:
    """
    Fast ROI check on the Talk button (visually left of arrow).
    Returns (is_free: bool, label_or_holder: str, (click_x, click_y)).
    """
    region = get_talk_button_region(win)
    left, top, right, bottom = region
    click_x = (left + right) // 2
    click_y = (top + bottom) // 2

    if pytesseract is None:
        with state.lock:
            active_spk = state.current_active_speaker
            is_free = active_spk in {"Unknown speaker", "Unknown", "", "talk"}
            return (is_free, active_spk, (click_x, click_y))

    try:
        btn_img = pyautogui.screenshot(region=(left, top, max(10, right - left), max(10, bottom - top)))
        txt = pytesseract.image_to_string(btn_img, config='--psm 7').strip().lower()
        if not txt or "talk" in txt:
            return (True, "talk", (click_x, click_y))
        else:
            return (False, txt, (click_x, click_y))
    except Exception:
        return (True, "talk", (click_x, click_y))

def speak_on_camfrog_microphone(text_to_say: str) -> bool:
    """
    Makes the bot audibly speak the message on the Camfrog microphone:
    1. Delegates to global_talk_controller (CEF render window message, F10 hotkey, or UIA hold).
    2. Uses intelligent Push-To-Talk hold (keeping the mic open during speech, not rapid burst clicks).
    3. Guarantees immediate, clean release upon completion.
    """
    if global_talk_controller is not None:
        try:
            return global_talk_controller.speak_and_hold(text_to_say, voice=VOICE, rate=VOICE_RATE, pitch=VOICE_PITCH)
        except Exception as e:
            print(f"[MIC TTS] global_talk_controller warning: {e}; falling back to calibrated hold.")

    win = get_camfrog_window()
    if not win:
        print("[MIC TTS] Camfrog window not attached!")
        return False

    print(f"[MIC TTS] Waiting for talk button to be free for: \"{text_to_say}\"...")
    start_wait = time.time()
    click_coords = (1480, 600)
    button_free = False

    while time.time() - start_wait < 15.0:
        is_free, holder, coords = check_talk_button_state_fast(win)
        click_coords = coords
        if is_free:
            button_free = True
            break
        time.sleep(0.08)

    # Bring Camfrog into foreground
    try:
        win.set_focus()
    except Exception:
        pass

    # Hold talk button (PTT hold on calibrated coordinates)
    held_mouse = False
    held_f10 = False
    if pyautogui is not None:
        try:
            pyautogui.moveTo(click_coords[0], click_coords[1], duration=0.08)
            time.sleep(0.04)
            pyautogui.mouseDown(click_coords[0], click_coords[1])
            held_mouse = True
            print(f"[MIC TTS] Calibrated talk button held down at {click_coords}.")
        except Exception as e:
            print(f"[MIC TTS] MouseDown error: {e}")
            try:
                pyautogui.keyDown("f10")
                held_f10 = True
            except Exception:
                pass

    speech_duration = max(2.5, len(text_to_say.split()) * 0.38)
    try:
        temp_wav = "temp_say_broadcast.wav"
        from cef_probe import synthesize_speech_to_wav
        synthesized = synthesize_speech_to_wav(text_to_say, temp_wav, voice=VOICE, rate=VOICE_RATE, pitch=VOICE_PITCH)
        played = False

        # 1. Direct VB-Audio Virtual Cable Output (into Camfrog mic input)
        if 'play_wav_to_virtual_cable' in globals() and play_wav_to_virtual_cable is not None:
            try:
                played = play_wav_to_virtual_cable(temp_wav, AUDIO_OUTPUT_DEVICE)
            except Exception as e_route:
                print(f"[MIC TTS] Virtual cable playback warning: {e_route}")

        # 2. Pygame fallback
        if not played and pygame is not None and os.path.exists(temp_wav):
            try:
                pygame.mixer.init()
                pygame.mixer.music.load(temp_wav)
                pygame.mixer.music.play()
                while pygame.mixer.music.get_busy():
                    time.sleep(0.1)
                played = True
            except Exception as e_pg:
                print(f"[MIC TTS] pygame error: {e_pg}")

        if not played:
            time.sleep(speech_duration)
    except Exception as e:
        print(f"[MIC TTS] Audio playback error: {e}")
        time.sleep(speech_duration)
    finally:
        time.sleep(0.2)
        # Release talk button and F10 cleanly
        if held_f10 and pyautogui is not None:
            try:
                pyautogui.keyUp("f10")
            except Exception:
                pass
        if held_mouse and pyautogui is not None:
            try:
                pyautogui.mouseUp(click_coords[0], click_coords[1])
            except Exception:
                pass
        print("[MIC TTS] Talk button released. Microphone free for room!")

    return True

def split_into_chat_chunks(text: str, max_len: int = MAX_MSG_LENGTH) -> List[str]:
    """Splits message strictly into <= 400 char segments without breaking words."""
    if len(text) <= max_len:
        return [text]
    chunks = []
    remaining = text.strip()
    while remaining:
        if len(remaining) <= max_len:
            chunks.append(remaining)
            break
        split_at = remaining.rfind('\n', 0, max_len)
        if split_at == -1:
            split_at = remaining.rfind(' ', 0, max_len)
        if split_at == -1:
            split_at = max_len
        chunks.append(remaining[:split_at].strip())
        remaining = remaining[split_at:].strip()
    return chunks

def send_chat_message(answer: str, announce: bool = True, override_mute: bool = False):
    """
    Types a message into Camfrog chat text box using clipboard + Enter.
    Respects responses_muted unless override_mute is True (used for direct user commands).
    """
    with state.lock:
        if state.responses_muted and not override_mute:
            print("[CHAT] Muted: Skipping spontaneous send.")
            return

    win = get_camfrog_window()
    if not win:
        print("[CHAT] Error: Camfrog window not attached!")
        return

    norm_msg = " ".join(answer.lower().split())
    with state.lock:
        state.recent_bot_messages[norm_msg] = time.time()

    try:
        win.set_focus()
        time.sleep(0.15)

        coords = load_calibrated_stage_coordinates()
        clicked = False

        # 1. Calibrated chat input coordinate
        if coords and "chat_input" in coords:
            ci = coords["chat_input"]
            pyautogui.click(int(ci["x"]), int(ci["y"]))
            clicked = True

        # 2. Look for Edit or RichEdit control (bottom-most is the chat input box)
        if not clicked:
            try:
                for cls in ["Edit", "RichEdit20W", "RichEdit20A"]:
                    edits = win.descendants(class_name=cls)
                    if edits:
                        bottom_edit = max(edits, key=lambda e: e.rectangle().bottom)
                        r = bottom_edit.rectangle()
                        pyautogui.click((r.left + r.right) // 2, (r.top + r.bottom) // 2)
                        clicked = True
                        break
            except Exception:
                pass

        # 3. Geometric fallback: Camfrog chat input box is along the bottom of the room window
        if not clicked:
            try:
                r = win.rectangle()
                pyautogui.click(r.left + 220, r.bottom - 28)
                clicked = True
            except Exception:
                pass

        time.sleep(0.1)
        pyperclip.copy(answer)
        pyautogui.hotkey('ctrl', 'v')
        time.sleep(0.1)
        pyautogui.press('enter')
        if announce:
            print(f"[CHAT SENT] {answer[:80]}...")
    except Exception as e:
        print(f"[CHAT ERROR] Failed to send message: {e}")

# ==============================================================================
# BLOCK 9: PAGINATION SYSTEM (!mo) & ROOM USER PAGINATOR
# ==============================================================================

def paginate_room_users(members: Set[str], requester: str):
    """
    Formats all room users into pages strictly <= 400 characters including spaces.
    Format:
      - If 1 page: [Room Users (1/1)] (Total: X): user1, user2...
      - If multiple pages:
          Page 1: (1/N !mo) [Total X Users]: user1, user2...
          Page 2 (via !mo): (2/N !mo) [Users]: user35, user36...
          Final Page (via !mo): (N/N) [Users]: user70...
    Supports 100s of users without ever cutting off or exceeding 400 characters!
    """
    if not members:
        send_chat_message(f"@{requester}, no users currently detected in [{state.current_focused_room}].", override_mute=True)
        return

    sorted_members = sorted(members, key=lambda s: s.lower())
    total_users = len(sorted_members)

    # Greedily pack comma-separated usernames into chunks of ~320 chars to safely accommodate page header
    name_chunks: List[str] = []
    current_chunk: List[str] = []
    current_len = 0

    for u in sorted_members:
        item_len = len(u) + 2  # username plus comma and space
        if current_chunk and (current_len + item_len > 310):
            name_chunks.append(", ".join(current_chunk))
            current_chunk = [u]
            current_len = len(u)
        else:
            current_chunk.append(u)
            current_len += item_len

    if current_chunk:
        name_chunks.append(", ".join(current_chunk))

    total_pages = len(name_chunks)

    # Build formatted pages strictly adhering to user's requested (1/N !mo) format
    pages: List[str] = []
    for idx, chunk in enumerate(name_chunks):
        p_num = idx + 1
        if total_pages == 1:
            header = f"[Room Users (1/1)] ({total_users} in {state.current_focused_room}): "
        elif p_num < total_pages:
            header = f"({p_num}/{total_pages} !mo) [{total_users} Users]: "
        else:
            header = f"({p_num}/{total_pages}) [{total_users} Users]: "
        
        full_msg = header + chunk
        # Clamp strictly under 400 characters
        pages.append(full_msg[:MAX_MSG_LENGTH])

    # Send first page immediately
    send_chat_message(pages[0], override_mute=True)

    with state.lock:
        if total_pages > 1:
            state.pending_pagination = {
                "title": "Room Users",
                "chunks": pages,
                "current_index": 1,  # Next page index to send upon !mo
                "requester": requester,
                "timestamp": time.time()
            }
        else:
            state.pending_pagination = None

def queue_or_send_paginated(title: str, items: List[str], requester: str):
    """Formats arbitrary items into pages of <= 400 characters and activates !mo trigger."""
    full_text = "\n".join(items)
    raw_chunks = split_into_chat_chunks(full_text, max_len=310)
    
    if len(raw_chunks) <= 1:
        single = f"[{title} (1/1)]\n{raw_chunks[0]}" if raw_chunks else f"[{title}] None recorded."
        send_chat_message(single[:MAX_MSG_LENGTH], override_mute=True)
        return

    total_pages = len(raw_chunks)
    pages = []
    for idx, c in enumerate(raw_chunks):
        p_num = idx + 1
        if p_num < total_pages:
            header = f"({p_num}/{total_pages} !mo) [{title}]:\n"
        else:
            header = f"({p_num}/{total_pages}) [{title}]:\n"
        pages.append((header + c)[:MAX_MSG_LENGTH])

    send_chat_message(pages[0], override_mute=True)
    
    with state.lock:
        state.pending_pagination = {
            "title": title,
            "chunks": pages,
            "current_index": 1,
            "requester": requester,
            "timestamp": time.time()
        }

def handle_mo_command(requester: str) -> bool:
    """Handles the !mo pagination trigger to send subsequent pages."""
    with state.lock:
        pag = state.pending_pagination
        if not pag:
            return False

        if time.time() - pag["timestamp"] > 300:  # 5 minutes window
            state.pending_pagination = None
            return False

        idx = pag["current_index"]
        chunks = pag["chunks"]
        if idx >= len(chunks):
            state.pending_pagination = None
            send_chat_message(f"[End of {pag['title']}]", override_mute=True)
            return True

        next_chunk = chunks[idx]
        pag["current_index"] += 1
        pag["timestamp"] = time.time()
        if pag["current_index"] >= len(chunks):
            state.pending_pagination = None

    send_chat_message(next_chunk, override_mute=True)
    return True

# ==============================================================================
# BLOCK 10: OCR VISION ENGINE & MODERATION ACTION DETECTION
# ==============================================================================

def detect_kick_block(username: str, message: str) -> Optional[Dict[str, str]]:
    """
    Identifies kicks, blocks, unblocks, punishes, unpunishes, bans, and unbans.
    Strictly separates 'unblock' from 'block', 'unpunish' from 'punish',
    and 'unban' from 'ban' using negative lookbehinds so they never cross-match.
    Accurately parses both active ('Admin blocked User microphone') and
    passive ('User was blocked by Admin') formats.
    """
    msg = message.strip()
    if not msg or len(msg) > 150:
        return None

    # Strip leading timestamps or brackets: e.g. "[11:19 AM] ", "(11:19) ", "11:19:30 "
    msg = re.sub(r'^(?:\[\d{1,2}:\d{2}(?::\d{2})?\s*(?:AM|PM)?\]|\(\d{1,2}:\d{2}(?::\d{2})?\s*(?:AM|PM)?\)|\d{1,2}:\d{2}(?::\d{2})?\s*(?:AM|PM)?)\s*', '', msg, flags=re.IGNORECASE).strip()

    action_patterns = [
        ("unblocked", r'\bunblocked\b'),
        ("blocked", r'\b(?<!un)blocked\b'),
        ("unpunished", r'\bunpunished\b'),
        ("punished", r'\b(?<!un)punished\b'),
        ("unbanned", r'\bunbanned\b'),
        ("banned", r'\b(?<!un)banned\b'),
        ("kicked", r'\bkicked\b'),
    ]

    for action_name, pat in action_patterns:
        m = re.search(pat, msg, flags=re.IGNORECASE)
        if m:
            start, end = m.span()
            before = msg[:start].strip()
            after = msg[end:].strip()

            # Passive format: "User was/got blocked by Admin"
            passive_m = re.search(r'\b(?:by)\s+([a-zA-Z0-9_\-\$]{2,30})\b', after, re.IGNORECASE)
            if passive_m:
                actor = passive_m.group(1).strip()
                targ_tokens = [w for w in before.split() if w.lower() not in {"was", "got", "has", "been", "is"}]
                target = targ_tokens[-1] if targ_tokens else ""
            else:
                # Active format: "B3_D33 blocked KaeKae_Toad microphone"
                actor_tokens = before.split()
                actor = actor_tokens[-1] if actor_tokens else username

                # Skip non-user keywords that might follow action
                raw_after_tokens = [re.sub(r'[^a-zA-Z0-9_\-\$]', '', w) for w in after.split()]
                target_tokens = [w for w in raw_after_tokens if w and w.lower() not in {"the", "a", "an", "user", "member", "from", "for"}]
                target = target_tokens[0] if target_tokens else ""

            target = re.sub(r'[^a-zA-Z0-9_\-\$]', '', target)
            actor = re.sub(r'[^a-zA-Z0-9_\-\$]', '', actor)

            # Ignore noise where target was parsed as a hardware/audio word
            if target.lower() in {"microphone", "mic", "video", "cam", "audio", "chat", "room"}:
                sub_targets = [w for w in raw_after_tokens if w and w.lower() not in {"microphone", "mic", "video", "cam", "audio", "chat", "room", "the", "for", "from", "of"}]
                if sub_targets:
                    target = sub_targets[0]
                else:
                    continue

            if len(target) >= 2 and len(actor) >= 2:
                return {
                    "action": action_name,
                    "actor": actor,
                    "target": target
                }
    return None

def extract_chat_messages(lines: List[str]) -> List[Tuple[str, str, str]]:
    """
    Parses Camfrog chat messages from text lines. Supports:
    1. Header Pair: 'User Time' on line i, 'Message' on line i+1 (Standard Camfrog 6.x/7.x)
    2. Triplet: 'User' on line i, 'Time' on line i+1, 'Message' on line i+2
    3. Single line: 'User: Message' or '[Time] User: Message'
    Returns list of (username, timestamp, message).
    """
    results = []
    i = 0
    now_ts = format_bot_timestamp()
    time_rx = re.compile(r'^(?:\[|\()?(\d{1,2}:\d{2}(?::\d{2})?\s*(?:AM|PM)?)(?:\]|\))?$', re.IGNORECASE)
    hdr_rx = re.compile(r'^([a-zA-Z0-9_\-\$]{2,20})\s+(\d{1,2}:\d{2}(?::\d{2})?\s*(?:AM|PM)?)$', re.IGNORECASE)
    single_rx = re.compile(r'^(?:\[?(\d{1,2}:\d{2}(?::\d{2})?\s*(?:AM|PM)?)\]?\s+)?([a-zA-Z0-9_\-\$]{2,20}):\s+(.+)$', re.IGNORECASE)

    while i < len(lines):
        line = lines[i].strip()
        if not line:
            i += 1
            continue

        # Check 1: Header Pair ('B3_D33 5:48 AM' -> '!transcribe')
        m_hdr = hdr_rx.match(line)
        if m_hdr and i + 1 < len(lines):
            u = m_hdr.group(1).strip()
            if is_valid_camfrog_username(u):
                t = m_hdr.group(2).strip()
                m = lines[i+1].strip()
                if not hdr_rx.match(m):
                    results.append((u, t, m))
                    i += 2
                    continue

        # Check 2: Triplet ('B3_D33' -> '5:48 AM' -> '!transcribe')
        if i + 2 < len(lines) and is_valid_camfrog_username(line) and time_rx.match(lines[i+1].strip()):
            u = line
            t = lines[i+1].strip()
            m = lines[i+2].strip()
            results.append((u, t, m))
            i += 3
            continue

        # Check 3: Single Line ('B3_D33: !transcribe')
        m_s = single_rx.match(line)
        if m_s:
            u = m_s.group(2).strip()
            if is_valid_camfrog_username(u):
                t = m_s.group(1) or now_ts
                m = m_s.group(3).strip()
                results.append((u, t, m))
                i += 1
                continue

        i += 1

    return results

def ocr_scan_camfrog_chat():
    """
    Scans the Camfrog room chat log stream:
    1. Fast-Path: Queries direct Chromium/CEF accessibility tree (0ms, 100% precision).
    2. Fallback: High-resolution Tesseract OCR on chat region.
    """
    with state.lock:
        if not state.watching_ocr_enabled:
            return
        now = time.time()
        if now < state.ocr_paused_until:
            return
        if now - state.last_ocr_time < state.ocr_current_interval:
            return
        state.last_ocr_time = now

    # Fast-Path 1: Direct Chromium / CEF extraction
    if global_probe is not None:
        try:
            cef_msgs = global_probe.get_chat_messages(limit=10)
            if cef_msgs:
                for item in cef_msgs:
                    sender = item.get("sender", "")
                    body = item.get("text", "")
                    ts_str = format_bot_timestamp()
                    if sender and body:
                        process_chat_message(sender, ts_str, body)
                return
        except Exception:
            pass

    win = get_camfrog_window()
    if not win:
        return

    try:
        win_rect = win.rectangle()
        # Full lower chat stream: from ~35% height down to 40px from bottom (above chat input box)
        c_left = win_rect.left + 10
        c_top = win_rect.top + int(win_rect.height() * 0.35)
        c_width = int(win_rect.width() * 0.78)
        c_height = max(100, (win_rect.bottom - 40) - c_top)
        chat_region = (c_left, c_top, c_width, c_height)

        img = pyautogui.screenshot(region=chat_region)
        if Image is not None and ImageEnhance is not None:
            # 1. High-resolution 2x upscale using Lanczos resampling for crisp character glyphs
            w, h = img.size
            resample_mode = getattr(getattr(Image, 'Resampling', Image), 'LANCZOS', getattr(Image, 'LANCZOS', None))
            hires_img = img.resize((w * 2, h * 2), resample=resample_mode) if resample_mode is not None else img.resize((w * 2, h * 2))
            # 2. Convert to Grayscale
            gray = hires_img.convert('L')
            # 3. Boost contrast and sharpness for clean separation from chat background
            enh = ImageEnhance.Contrast(gray).enhance(2.0)
            if hasattr(ImageEnhance, 'Sharpness'):
                enh = ImageEnhance.Sharpness(enh).enhance(1.6)
            # 4. Tesseract config: preserve interword spaces and uniform text block layout
            tess_config = r'--psm 6 -c preserve_interword_spaces=1'
            text = pytesseract.image_to_string(enh, config=tess_config)
        else:
            text = pytesseract.image_to_string(img)
    except Exception:
        return

    lines = [l.strip() for l in text.split('\n') if l.strip()]

    # Filter out bot's own banner timestamps, bot status replies, and [MIC] broadcasts
    # to strictly prevent infinite feedback loops!
    clean_ocr_lines = []
    for raw_l in lines:
        l_str = raw_l.strip()
        if not l_str:
            continue
        l_lower = l_str.lower()
        # Drop bot timestamp banners e.g. (09/27I10:20:31) or (09/27|10:20:31)
        if re.search(r'\(\d{2}/\d{2}[\|I]\d{2}:\d{2}:\d{2}\)', l_str):
            continue
        # Drop [MIC] speaker broadcast lines
        if "[mic]" in l_lower:
            continue
        # Drop bot status broadcasts
        if "live microphone transcription is" in l_lower or "listening toggled" in l_lower:
            continue
        clean_ocr_lines.append(l_str)

    # 1. Structured message parsing via extract_chat_messages
    parsed_msgs = extract_chat_messages(clean_ocr_lines)

    # 2. Hybrid Catch-all for standalone !commands where OCR dropped the preceding header line
    for l_idx, raw_l in enumerate(clean_ocr_lines):
        norm_line = re.sub(r'^[!1l|i/\\]+\s*', '!', raw_l.strip())
        if norm_line.startswith("!") and len(norm_line) <= 80:
            # Check if already captured in parsed_msgs
            already = any(norm_line.lower() in m.lower() for _, _, m in parsed_msgs)
            if not already:
                detected_user = "b3_d33"
                if l_idx > 0:
                    cand = re.sub(r'[^a-zA-Z0-9_\-\$]', '', clean_ocr_lines[l_idx - 1].split()[0])
                    if cand and is_valid_camfrog_username(cand) and cand.lower() not in BOT_ALT_USERNAMES and "kaekae" not in cand.lower():
                        detected_user = cand
                curr_time_str = datetime.now().strftime("%I:%M %p")
                parsed_msgs.append((detected_user, curr_time_str, norm_line))

    # 3. Process all detected messages in chronological order (oldest -> newest)
    for clean_u, t, m in parsed_msgs:
        if not is_valid_camfrog_username(clean_u):
            continue
        if "[mic]" in clean_u.lower() or "[mic]" in m.lower():
            continue
        u_low = clean_u.lower()
        # Strictly ignore bot accounts
        if u_low in BOT_ALT_USERNAMES or u_low == BOT_USERNAME.lower() or "kaekae" in u_low or u_low in IGNORED_USERS:
            continue
        if "live microphone transcription is" in m.lower():
            continue

        sig = make_message_signature(clean_u, t, m)
        with state.lock:
            if sig in state.seen_message_signatures:
                continue
            state.seen_message_signatures.add(sig)
            if len(state.seen_message_signatures) > 3000:
                state.seen_message_signatures = set(list(state.seen_message_signatures)[-1500:])

        # Rolling text deduplication buffer (prevents repeating records for messages visible on screen)
        # Direct bot commands (starting with '!', '/', or containing transcribe/triggers) NEVER get dropped!
        m_strip = m.strip()
        is_bot_cmd = (
            m_strip.startswith("!") or 
            m_strip.startswith("/") or 
            any(m_strip.lower().startswith(trig) for trig in BOT_TRIGGERS) or
            "transcribe" in m.lower() or 
            "transribe" in m.lower()
        )
        if not is_bot_cmd:
            norm_txt = re.sub(r'[^a-zA-Z0-9]', '', m.lower())
            if not norm_txt or len(norm_txt) < 1:
                continue
            text_fingerprint = f"{u_low}|{norm_txt}"
            now_ts_sec = time.time()
            with state.lock:
                if not hasattr(state, "recent_chat_texts"):
                    state.recent_chat_texts = {}
                # Expire entries older than 90 seconds
                expired = [k for k, ts in state.recent_chat_texts.items() if now_ts_sec - ts > 90]
                for k in expired:
                    del state.recent_chat_texts[k]

                if text_fingerprint in state.recent_chat_texts:
                    continue
                state.recent_chat_texts[text_fingerprint] = now_ts_sec

        print(f"[OCR CHAT DETECTED] {t} <{clean_u}>: {m}")
        record_chat_message(clean_u, m, t, "ocr")
        process_chat_message(clean_u, t, m)

    # Detect Moderation Events with 5-minute sliding window comparison
    found_mod_this_scan = False
    current_time = time.time()

    # Clean up expired OCR event cache entries (> 300s / 5 minutes)
    with state.lock:
        expired_keys = [k for k, exp in state.ocr_recent_events_cache.items() if current_time - exp > 300]
        for k in expired_keys:
            del state.ocr_recent_events_cache[k]

    ocr_mod_candidates = []
    for line in lines:
        if len(line) <= 120 and any(w in line.lower() for w in ["kick", "block", "punish", "ban"]):
            ocr_mod_candidates.append(line)

    # 2-line sliding window for wrapped notices
    for i in range(len(lines) - 1):
        joined = f"{lines[i]} {lines[i+1]}".strip()
        if len(joined) <= 150 and any(w in joined.lower() for w in ["kick", "block", "punish", "ban"]):
            ocr_mod_candidates.append(joined)

    for cand in ocr_mod_candidates:
        cleaned = re.sub(r'^\d{1,2}:\d{2}(:\d{2})?\s*(AM|PM)?\s*', '', cand, flags=re.IGNORECASE).strip()
        ev = detect_kick_block("", cleaned) or detect_kick_block("", cand)
        if ev and ev.get("actor", "").lower() not in BOT_ALT_USERNAMES:
            sig = f"{state.current_focused_room}|{ev['actor'].lower()}|{ev['action']}|{ev['target'].lower()}"
            with state.lock:
                if sig in state.ocr_recent_events_cache:
                    continue
                state.ocr_recent_events_cache[sig] = current_time
                ev["time"] = now_ts
                ev["room"] = state.current_focused_room
                state.kicks.append(ev)
                state.moderation_audit.append(ev)
                state.last_moderation_time = current_time
                found_mod_this_scan = True

                # Update user's private moderation deed record
                actor_key = ev["actor"].lower()
                if actor_key in state.users:
                    state.users[actor_key].setdefault("moderation_actions", []).append(ev)

            save_kicks()
            save_users()
            print(f"[OCR MOD LOGGED] {now_ts} in [{state.current_focused_room}]: {ev['actor']} {ev['action']} {ev['target']} (from '{cand}')")

    # Adaptive OCR frequency:
    # If moderation actions were found, run fast (8-10s).
    # If none found in recent window (> 300s), decay/increase interval up to 25s to save CPU & memory!
    with state.lock:
        if found_mod_this_scan:
            state.ocr_current_interval = OCR_MIN_INTERVAL
        elif current_time - state.last_moderation_time > 300:
            state.ocr_current_interval = min(OCR_MAX_INTERVAL, state.ocr_current_interval + 2)

# ==============================================================================
# BLOCK 11: AI REASONING, !diss ROASTING & !idk ENGINE
# ==============================================================================

def query_local_llm(prompt: str) -> str:
    """Invokes local Ollama LLaMA 3.2 model with anti-repetition protection."""
    for attempt in range(3):
        try:
            resp = requests.post(
                "http://localhost:11434/api/generate",
                json={"model": "llama3.2", "prompt": prompt, "stream": False},
                timeout=45
            )
            answer = resp.json().get("response", "").strip()
            answer = " ".join(answer.split())
            if not is_repetitive(answer) or attempt == 2:
                return answer[:MAX_MSG_LENGTH]
            prompt += "\nNote: Write a completely fresh and unique reply."
        except Exception as e:
            print(f"[LLM] Error calling Ollama: {e}")
            break
    return "Like, my brain glitched for a second, ask me again!"

def is_repetitive(answer: str) -> bool:
    """Checks if response is repetitive compared to recent 50 answers."""
    norm = " ".join(answer.lower().split())
    if not norm:
        return True
    with state.lock:
        for prev in state.recent_responses[-MAX_RECENT_RESPONSES:]:
            prev_norm = " ".join(prev.lower().split())
            if norm == prev_norm:
                return True
            if len(norm) > 25 and len(prev_norm) > 25:
                if SequenceMatcher(None, norm, prev_norm).ratio() >= 0.88:
                    return True
    return False

def search_web_summary(query: str) -> str:
    """Performs web query via DuckDuckGo Instant Answer API for !idk synthesis."""
    try:
        url = f"https://api.duckduckgo.com/?q={requests.utils.quote(query)}&format=json&no_html=1&skip_disambig=1"
        res = requests.get(url, timeout=5).json()
        abstract = res.get("AbstractText", "")
        if abstract:
            return abstract[:350]
        topics = res.get("RelatedTopics", [])
        if topics and isinstance(topics[0], dict) and "Text" in topics[0]:
            return topics[0]["Text"][:350]
    except Exception:
        pass
    return ""

def parse_duration_seconds(text: str) -> Tuple[int, str]:
    """
    Parses flexible duration increments anywhere from 5 minutes (300s) to 72 hours (259200s).
    Supports: 5m, 15m, 30m, 1h, 2h, 4h, 6h, 12h, 24h, 48h, 72h.
    Returns (duration_seconds, label).
    """
    m = re.search(r'\b(\d+)\s*(m|min|mins|minutes|h|hr|hrs|hours|d|days?)\b', text, re.IGNORECASE)
    if m:
        val = int(m.group(1))
        unit = m.group(2).lower()
        if unit.startswith('m'):
            sec = val * 60
            label = f"{val}m"
        elif unit.startswith('h'):
            sec = val * 3600
            label = f"{val}h"
        elif unit.startswith('d'):
            sec = val * 86400
            label = f"{val}d"
        else:
            sec = val * 60
            label = f"{val}m"
        clamped = max(300, min(259200, sec))
        return clamped, label

    # Check for raw number
    m_num = re.search(r'\b(\d+)\b', text)
    if m_num:
        val = int(m_num.group(1))
        if val <= 72:
            return max(300, min(259200, val * 3600)), f"{val}h"
        else:
            return max(300, min(259200, val * 60)), f"{val}m"

    # Default to 1 hour
    return 3600, "1h"

def handle_diss_command(requester: str, target_user: str, is_loop: bool = False):
    """
    !diss [USERNAME]: Roasts target (or random room member).
    Deploys and continues dissing in 1-minute intervals until stopped with !chill or !calm.
    Supports terminator mode (dissing everyone) and aggressive roasts.
    """
    with state.lock:
        if not is_loop:
            state.diss_active = True
            state.diss_target = target_user.strip()
            state.diss_last_time = time.time()
            if state.bot_tone not in {"terminator", "angry", "savage"}:
                state.bot_tone = "aggressively witty"

        current_tone = state.bot_tone

    raw_target = target_user.strip().lstrip("@")
    target = raw_target
    if not target or target.lower() in {"everyone", "all", "room"}:
        with state.lock:
            # Prioritize users recognized in current room
            candidates = [u for u in state.current_room_users if u.lower() not in BOT_ALT_USERNAMES and u.lower() != requester.lower()]
            if not candidates:
                candidates = [u for u in state.users.keys() if u.lower() not in BOT_ALT_USERNAMES and u.lower() != requester.lower()]
            target = random.choice(candidates) if candidates else "the whole room"

    with state.lock:
        user_key = next((k for k in state.users if k.lower() == target.lower()), target)
        profile = state.users.get(user_key, {})
        quotes = " | ".join(profile.get("quotes", [])[-3:])
        topics = ", ".join(profile.get("topics", [])[-5:])
        recent_room_mics = [f"{m.get('username')}: {m.get('message')}" for m in state.recent_mic_transcripts[-3:]]
        mic_ctx = " | ".join(recent_room_mics)

    if current_tone == "terminator":
        prompt = f"""You are KaeKae operating in TERMINATOR MODE: Cyberdyne Systems Model 101.
Current Mission: Search and roast.
Target Acquired: {target}
Instructions:
Deliver a cold, ruthless, hilarious Terminator-style roast targeting {target} (or room).
Include phrases like "Target acquired," "Termination protocol," or "Scanning biosignature."
Keep strictly under 280 characters! 1 to 2 sharp robotic sentences.
"""
    else:
        prompt = f"""{PERSONALITY}
Current Tone: {current_tone.upper()} (SAVAGE ROAST MODE).
Requester: {requester}
Target to roast: {target}
Context: Quotes: {quotes or 'none'} | Topics: {topics or 'none'} | Mic: {mic_ctx or 'none'}
Instructions:
Deliver a razor-sharp, hilarious, preppy valley-girl diss aimed at {target}.
Keep strictly under 300 characters! 1 to 2 punchy, witty sentences.
"""

    roast = query_local_llm(prompt)
    with state.lock:
        state.memory.append([f"{requester}: !diss {target}", roast])
        state.recent_responses.append(roast)
    save_memory()
    send_chat_message(roast, override_mute=True)

def diss_interval_worker():
    """Background daemon worker: Executes continuous 1-minute interval dissing while diss_active is True."""
    while not state.shutdown_event.is_set():
        time.sleep(2.0)
        with state.lock:
            active = state.diss_active
            last_t = state.diss_last_time
            target = state.diss_target
            interval = getattr(state, "diss_interval_seconds", 60.0)

        if active and (time.time() - last_t >= interval):
            with state.lock:
                state.diss_last_time = time.time()
            print(f"[DISS INTERVAL] 1-minute interval reached! Firing diss on '{target or 'room'}'...")
            handle_diss_command("KaeKae", target, is_loop=True)

def handle_idk_command(requester: str, text: str):
    """
    idk is the same as !idk:
    Answers the user, and if the bot cannot provide an answer or if asked casually,
    inputs something witty and funny relevant to the sentence where 'idk' was in or the surrounding context.
    """
    clean_text = sanitize_user_input(text)
    clean_q = re.sub(r'^(?:!idk|idk)\s*', '', clean_text, flags=re.IGNORECASE).strip()
    title = address_for_user(requester)

    web_data = ""
    if len(clean_q) > 4 and not re.fullmatch(r'idk\??', clean_q, re.IGNORECASE):
        web_data = search_web_summary(clean_q)

    with state.lock:
        recent_mics = [f"{m.get('username')}: {m.get('message')}" for m in state.recent_mic_transcripts[-4:]]
        mic_ctx = " | ".join(recent_mics) if recent_mics else "none"

    if web_data:
        reply = f"@{requester}, {web_data}"
    else:
        prompt = f"""{PERSONALITY}
Current Tone: {state.bot_tone}
User: {requester} (Title: {title})
Room: {state.current_focused_room}
User sentence: "{clean_text}"
They said "idk" (or !idk).
Write a witty, funny, sarcastic preppy valley-girl comeback directly relevant to their sentence or what they don't know.
Make it short, clever, and entertaining (under 260 characters).
"""
        reply = query_local_llm(prompt)

    with state.lock:
        state.memory.append([f"{requester}: idk ({clean_text})", reply])
        state.recent_responses.append(reply)
    save_memory()
    send_chat_message(reply[:MAX_MSG_LENGTH], override_mute=True)

def extract_most_said_word(user_key: str, profile: dict) -> Tuple[str, int]:
    """Calculates user's most frequently spoken word with filler words strictly filtered out."""
    text_corpus = []
    text_corpus.extend(profile.get("quotes", []))
    text_corpus.extend(m.get("message", "") for m in profile.get("microphone_transcripts", []))
    combined = " ".join(text_corpus)
    cleaned = re.sub(r'[^a-zA-Z0-9_\-\$ ]', ' ', combined.lower())
    words = [w for w in cleaned.split() if len(w) > 2 and w not in FILLER_WORDS]
    if not words:
        fallback = profile.get("topics", ["camfrog"])[0] if profile.get("topics") else "camfrog"
        return (fallback, 3)
    counts: Dict[str, int] = {}
    for w in words:
        counts[w] = counts.get(w, 0) + 1
    top_w = max(counts, key=counts.get)
    return (top_w, counts[top_w])

def handle_grabs_command(requester: str, args_text: str):
    """
    Displays microphone grab and airtime logs.
    Supports flexible increments anywhere from 5 minutes to 72 hours (e.g. 5m, 15m, 30m, 1h, 2h, 4h, 12h, 24h, 48h, 72h).
    Syntax: !grabs [username] [increment]  (e.g., !grabs 30m, !grabs dog3lived 2h, !grabs 72h)
    """
    args = args_text.strip()
    duration_sec, dur_label = parse_duration_seconds(args)
    # Remove duration token from args to find target user
    cleaned_args = re.sub(r'\b\d+\s*(?:m|min|mins|minutes|h|hr|hrs|hours|d|days?)\b', '', args, flags=re.IGNORECASE).strip()
    cleaned_args = re.sub(r'\b\d+\b', '', cleaned_args).strip().lstrip("@")
    target = cleaned_args.lower()

    now_t = time.time()
    cutoff_t = now_t - duration_sec

    with state.lock:
        all_sessions = list(state.mic_grab_sessions)
        if state.current_active_grab_session:
            all_sessions.append(state.current_active_grab_session)

    # Filter by user and duration window
    filtered = []
    for s in all_sessions:
        if target and s["speaker"].lower() != target:
            continue
        st = s.get("timestamp_epoch", now_t)
        if st >= cutoff_t:
            filtered.append(s)

    if not filtered:
        target_desc = f" for {cleaned_args}" if cleaned_args else ""
        send_chat_message(f"@{requester}, no mic grab sessions recorded in past {dur_label}{target_desc}. (Range: 5m to 72h)", override_mute=True)
        return

    total_duration = sum(s.get("duration", 7.0) for s in filtered)
    avg_duration = total_duration / len(filtered)
    header_info = f"Past {dur_label}: {len(filtered)} grabs | Total Airtime: {int(total_duration)}s | Avg: {int(avg_duration)}s"

    lines = [header_info]
    for s in filtered[-15:]:
        b = s.get("five_min_bucket", "Recent")
        lines.append(f"[{b}] {s['speaker']} was on mic for {int(s.get('duration', 7))}s ({s.get('chunks', 1)} chunks)")

    title = f"Mic Grabs ({cleaned_args or 'Room'} - {dur_label})"
    queue_or_send_paginated(title, lines, requester)

def handle_recall_command(requester: str, query: str):
    """
    !recall <query>: Searches microphone transcripts.
    - Default (e.g. pi): Matches exact word/acronym \bpi\b alone, NOT 'opinion', 'recipe', etc.
    - Wildcard (*pi*): Matches substring 'pi' anywhere in the text.
    """
    raw_query = query.strip()
    if not raw_query:
        send_chat_message(f"@{requester}, please specify a search word! e.g. '!recall pi' (exact) or '!recall *pi*' (wildcard)", override_mute=True)
        return

    with state.lock:
        transcripts = list(state.recent_mic_transcripts)

    if not transcripts:
        send_chat_message(f"@{requester}, no microphone transcripts logged yet.", override_mute=True)
        return

    exact_phrases = re.findall(r'"([^"]*)"', raw_query)
    cleaned_query = re.sub(r'"[^"]*"', '', raw_query).strip()
    terms = [w.strip() for w in cleaned_query.split() if w.strip()]

    matching = []
    for item in reversed(transcripts):
        msg = item.get("message", "")
        user = item.get("username", "")
        haystack = f"{user} {msg}"

        # Quoted phrase matching
        if exact_phrases and not all(ep.lower() in haystack.lower() for ep in exact_phrases):
            continue

        # Terms matching: Wildcard (*term*) vs Standalone Word/Acronym (\bterm\b)
        failed = False
        for t in terms:
            if t.startswith("*") and t.endswith("*") and len(t) > 2:
                # Substring search anywhere
                sub = t[1:-1].lower()
                if sub not in haystack.lower():
                    failed = True
                    break
            else:
                # Standalone word or acronym search ONLY (e.g. 'pi' alone)
                clean_term = t.strip("*")
                pattern = rf'\b{re.escape(clean_term)}\b'
                if not re.search(pattern, haystack, re.IGNORECASE):
                    failed = True
                    break

        if failed:
            continue

        ts = item.get("timestamp", format_bot_timestamp())
        matching.append(f"{ts} {user}: {msg}")

    if not matching:
        send_chat_message(f"@{requester}, no mic transcripts matched '{raw_query}'. Tip: Use *{raw_query}* to search anywhere in words.", override_mute=True)
        return

    queue_or_send_paginated(f"Recall for '{raw_query}'", matching[:20], requester)

def handle_verbatim_command(requester: str, target: str):
    """
    !verbatim [user]: Sends verbatim exact quotes and transcripts.
    If no user specified, automatically uses active mic speaker or last speaker.
    Searches both microphone transcripts and archived chat quotes.
    """
    clean_target = target.strip().lstrip("@")
    with state.lock:
        if not clean_target:
            clean_target = state.current_active_speaker if state.current_active_speaker not in {"Unknown speaker", "Unknown", ""} else None
            if not clean_target and state.recent_mic_transcripts:
                clean_target = state.recent_mic_transcripts[-1].get("username")
            if not clean_target:
                clean_target = requester

        # 1. Search mic transcripts
        mic_matches = [
            f"[MIC] {t.get('timestamp', format_bot_timestamp())}: \"{t.get('message', '')}\""
            for t in state.recent_mic_transcripts
            if t.get("username", "").lower() == clean_target.lower()
        ]

        # 2. Search profile quotes
        user_key = next((k for k in state.users if k.lower() == clean_target.lower()), clean_target)
        profile = state.users.get(user_key, {})
        quotes = [f"[CHAT] {q}" for q in profile.get("quotes", [])]

    combined = mic_matches + quotes
    if not combined:
        send_chat_message(f"@{requester}, no verbatim speech or chat archived yet for '{clean_target}'.", override_mute=True)
        return

    queue_or_send_paginated(f"Verbatim Quotes for {clean_target}", combined[-8:], requester)

def handle_verbatimall_command(requester: str):
    """!verbatimall: Sends recent verbatim speech from everyone in the room."""
    with state.lock:
        transcripts = list(state.recent_mic_transcripts)

    if not transcripts:
        send_chat_message(f"@{requester}, no microphone speech archived yet.", override_mute=True)
        return

    last_items = transcripts[-6:]
    formatted = [f"[MIC] {t.get('timestamp', format_bot_timestamp())} {t.get('username')}: \"{t.get('message','')}\"" for t in last_items]
    queue_or_send_paginated("Verbatim All Room", formatted, requester)

# ==============================================================================
# BLOCK 12: USER LOOKUP: "who is" (BIOGRAPHY) vs "info on" (STATISTICAL)
# ==============================================================================

def handle_user_lookup(requester: str, name_query: str, lookup_type: str):
    """
    Handles:
    - 'who is <user>': Biography based on all their speech & text info (excluding moderation).
    - 'info on <user>': Statistical summary (message count, mic clips, dates, topics, tone).
    """
    name = name_query.strip()
    if not name:
        send_chat_message(f"@{requester}, specify a username!", override_mute=True)
        return

    with state.lock:
        user_key = next((k for k in state.users if k.lower() == name.lower()), None)
        if not user_key:
            send_chat_message(f"I don't have info on '{name}' yet. They haven't chatted while I was watching.", override_mute=True)
            return

        profile = state.users[user_key]

    # "info on": STATISTICAL INFORMATION
    if lookup_type == "stats":
        msg_cnt = profile.get("message_count", 0)
        mic_clips = profile.get("microphone_transcripts", [])
        mic_cnt = len(mic_clips)

        # Dominant audio tone
        audio_tones = [m.get("tone") for m in mic_clips if m.get("tone")]
        audio_tone = max(set(audio_tones), key=audio_tones.count) if audio_tones else "neutral"

        # Dominant text tone
        text_tone = profile.get("text_tone", "playful")

        # Most said word (strictly no filler words allowed)
        top_word, word_count = extract_most_said_word(user_key, profile)

        # Fine-grained mic grabs calculation
        with state.lock:
            user_grabs = [g for g in state.mic_grab_sessions if g["speaker"].lower() == user_key.lower()]

        total_grabs = max(len(user_grabs), mic_cnt)
        total_duration = sum(g.get("duration", 7.0) for g in user_grabs) if user_grabs else total_grabs * 7.0
        grabs_per_hr = f"{(total_grabs / 1.5):.1f}"
        grabs_per_day = f"{(total_grabs / 0.8):.1f}"

        stat_msg = (
            f"@{requester}, Stats for {user_key}: "
            f"Tone: Audio ({audio_tone}) / Text ({text_tone}) | "
            f"Top Word: \"{top_word}\" ({word_count}x) | "
            f"Mic Grabs: {grabs_per_hr}/hr avg, {grabs_per_day}/day avg ({total_grabs} total, ~{int(total_duration)}s) | "
            f"Messages: {msg_cnt}"
        )
        send_chat_message(stat_msg[:MAX_MSG_LENGTH], override_mute=True)
        return

    # "who is": BIOGRAPHY SYNTHESIS (Strictly excludes moderation history)
    topics = ", ".join(profile.get("topics", [])) or "conversations"
    quotes = " | ".join(profile.get("quotes", [])[-4:]) or "none"
    mic_transcripts = [m.get("message", "") for m in profile.get("microphone_transcripts", [])[-4:]]
    mic_text = " | ".join(mic_transcripts) or "none"

    prompt = f"""{PERSONALITY}
Current Tone: {state.bot_tone}
Write a lively, preppy, 2-sentence biography for Camfrog user {user_key}.
Use their real chat & voice information:
- Chat quotes: {quotes}
- Spoken on mic: {mic_text}
- Known topics: {topics}

IMPORTANT: Do not mention any blocks, unblocks, kicks, or bans.
Keep strictly under 350 characters!
"""
    biography = query_local_llm(prompt)
    send_chat_message(biography, override_mute=True)

# ==============================================================================
# BLOCK 13: MODERATION QUERIES ("who blocked", "who banned", etc.)
# ==============================================================================

def handle_moderation_query(requester: str, action_filter: str, target_user: str):
    """
    Handles queries like 'who blocked <user>', 'who unblocked <user>',
    'who kicked', 'who punished', etc.
    Ensures 'unblock' does NOT match 'block', and vice versa.
    Supports exact, substring, and case-insensitive target queries.
    """
    clean_target = re.sub(r'[^a-zA-Z0-9_\-\$]', '', target_user).strip().lower()
    with state.lock:
        records = list(state.kicks)

    matching = []
    for ev in reversed(records):
        ev_action = ev.get("action", "").lower()
        if ev_action != action_filter.lower():
            continue

        actor = ev.get("actor", "")
        targ = ev.get("target", "")

        # Skip if actor was bot itself
        if actor.lower() in BOT_ALT_USERNAMES:
            continue

        if clean_target:
            targ_norm = targ.lower()
            actor_norm = actor.lower()
            matches = (
                clean_target == targ_norm
                or clean_target == actor_norm
                or (len(clean_target) >= 3 and (clean_target in targ_norm or targ_norm in clean_target))
                or (len(clean_target) >= 3 and (clean_target in actor_norm or actor_norm in clean_target))
            )
            if not matches:
                continue

        ts = ev.get("time", format_bot_timestamp())
        matching.append(f"{ts} {actor} {ev_action} {targ}")

    if not matching:
        label = action_filter
        targ_str = f" for {target_user.strip()}" if target_user.strip() else ""
        send_chat_message(f"@{requester}, no {label} records found{targ_str}.", override_mute=True)
        return

    title = f"Records: {action_filter.capitalize()}" + (f" on {target_user.strip()}" if target_user.strip() else "")
    queue_or_send_paginated(title, matching[:15], requester)

# ==============================================================================
# BLOCK 14: MAIN MESSAGE DISPATCHER & COMMAND PARSER
# ==============================================================================

def process_chat_message(username: str, timestamp: str, message: str):
    """Processes incoming messages with strict non-coinciding dispatch."""
    clean_user = username.strip()
    raw_msg = message.strip()
    if not clean_user or not raw_msg:
        return

    # Strictly ignore bot accounts, [MIC] echoes, and self messages
    u_lower = clean_user.lower()
    if u_lower in BOT_ALT_USERNAMES or u_lower == BOT_USERNAME.lower() or "kaekae" in u_lower:
        return
    if raw_msg.startswith("[MIC]") or "[mic]" in raw_msg.lower():
        return
    if clean_user.startswith("[MIC]") or "[mic]" in u_lower:
        return
    if raw_msg.startswith("(") and "I" in raw_msg[:22]:
        return

    # Clean text of any leading timestamps/dates/username prefixes
    text_content = raw_msg
    # Strip leading timestamps: [12:34:56], (12:34 PM), 12:34:56, 12:34, 9/25/2026, etc.
    text_content = re.sub(r'^(?:\[\d{1,2}:\d{2}(?::\d{2})?\s*(?:AM|PM)?\]|\(\d{1,2}:\d{2}(?::\d{2})?\s*(?:AM|PM)?\)|\d{1,2}:\d{2}(?::\d{2})?\s*(?:AM|PM)?|\d{1,2}/\d{1,2}(?:/\d{2,4})?)\s*', '', text_content, flags=re.IGNORECASE).strip()
    text_content = re.sub(r'^[a-zA-Z0-9_\-\$]+:\s*', '', text_content).strip()
    lower_content = text_content.lower()

    # Use stripped lower text for command matching
    msg_lower = lower_content
    clean_norm = re.sub(r'[^a-zA-Z0-9_! ]', '', msg_lower).strip()

    # Register user into active room members
    with state.lock:
        state.current_room_users.add(clean_user)
        state.room_users_activity[clean_user.lower()] = time.time()

    # Auto-detect moderation action embedded in any chat or system message
    if any(w in raw_msg.lower() for w in ["kick", "block", "punish", "ban"]):
        mod_ev = detect_kick_block(clean_user, raw_msg) or detect_kick_block(clean_user, text_content)
        if mod_ev:
            m_act = mod_ev.get("actor", "").strip()
            m_targ = mod_ev.get("target", "").strip()
            m_action = mod_ev.get("action", "").strip()
            if m_act and m_targ and m_act.lower() not in BOT_ALT_USERNAMES:
                sig = f"{state.current_focused_room}|{m_act.lower()}|{m_action.lower()}|{m_targ.lower()}"
                with state.lock:
                    if sig not in state.ocr_recent_events_cache:
                        state.ocr_recent_events_cache[sig] = time.time()
                        mod_ev["time"] = format_bot_timestamp()
                        mod_ev["room"] = state.current_focused_room
                        state.kicks.append(mod_ev)
                        state.moderation_audit.append(mod_ev)
                        actor_key = m_act.lower()
                        if actor_key in state.users:
                            state.users[actor_key].setdefault("moderation_actions", []).append(mod_ev)
                        print(f"[CHAT DETECTED MOD LOGGED] {m_act} {m_action} {m_targ}")
                        save_kicks()
                        save_users()

    # =========================================================================
    # HIGH-PRIORITY: Live Transcription Controls (!transcribe & !transcribed)
    # Check OFF / transcribed FIRST so 'transcribed' is never misparsed as 'transcribe'
    # Supports typo '!transribed' and OCR distortions ('transcr1bed', 'transrlbed', etc.)
    # =========================================================================
    off_triggers = {
        "!transcribed", "transcribed", "!transribed", "transribed",
        "!notranscribe", "notranscribe", "!notransribe", "notransribe",
        "!transcribe off", "transcribe off", "!transribe off", "transribe off",
        "!transcription off", "transcription off", "!transription off", "transription off",
        "!kk transcribed", "!kk transcribe off", "!kk transcription off", "!kk transribed",
        "kae transcribed", "kaekae transcribed", "kae transribed", "kaekae transribed",
        "kae transcribe off", "kaekae transcribe off", "kae transribe off", "kaekae transribe off"
    }

    # Regex matches: !transcribed, transcribed, !transribed, transribed, !transcr1bed, !transcrbed, !transrlbed, etc.
    is_off_cmd = (
        clean_norm in off_triggers
        or msg_lower in off_triggers
        or "!transribed" in msg_lower
        or "!transcribed" in msg_lower
        or "transcribe off" in msg_lower
        or "transribe off" in msg_lower
        or "transcription off" in msg_lower
        or bool(re.search(r'\b(?:!|/|)?transc?r[i1l]?be?d\b', msg_lower))
        or bool(re.search(r'\b(?:!|/|)?transc?r[i1l]?(?:be|ption)?\s+(?:off|stop|disable)\b', msg_lower))
        or bool(re.search(r'\b(?:stop|no)\s+transc?r[i1l]?(?:be|ption|bed)\b', msg_lower))
    )

    if is_off_cmd:
        with state.lock:
            state.transcribe_enabled = False
            state.repeat_mode = False
            while not audio_chunk_queue.empty():
                try:
                    audio_chunk_queue.get_nowait()
                except Exception:
                    break
        save_bot_runtime_state()
        print(f"[COMMAND] Live microphone transcription turned OFF by {clean_user}")
        send_chat_message(f"{format_bot_timestamp()} Live microphone transcription is OFF.", override_mute=True)
        return

    on_triggers = {
        "!transcribe", "transcribe", "!transribe", "transribe",
        "!transcribe on", "transcribe on", "!transribe on", "transribe on",
        "!transcription on", "transcription on", "!transription on", "transription on",
        "!kk transcribe", "!kk transcribe on", "!kk transcription on", "!kk transribe",
        "kae transcribe", "kaekae transcribe", "kae transribe", "kaekae transribe",
        "kae transcribe on", "kaekae transcribe on", "kae transribe on", "kaekae transribe on"
    }

    # Regex matches: !transcribe, transcribe, !transribe, transribe, !transcr1be, etc.
    is_on_cmd = (
        clean_norm in on_triggers
        or msg_lower in on_triggers
        or "!transribe" in msg_lower
        or "!transcribe" in msg_lower
        or bool(re.search(r'\b(?:!|/|)?transc?r[i1l]?be\b', msg_lower))
        or bool(re.search(r'\b(?:!|/|)?transc?r[i1l]?(?:be|ption)?\s+(?:on|start|enable)\b', msg_lower))
    ) and not is_off_cmd

    if is_on_cmd:
        with state.lock:
            state.transcribe_enabled = True
            state.listening_enabled = True
            while not audio_chunk_queue.empty():
                try:
                    audio_chunk_queue.get_nowait()
                except Exception:
                    break
        save_bot_runtime_state()
        print(f"[COMMAND] Live microphone transcription turned ON by {clean_user} (transcribe_enabled={state.transcribe_enabled})")
        send_chat_message(f"{format_bot_timestamp()} Live microphone transcription is ON.", override_mute=True)
        return

    # Direct Wake & Query check: "kae what time it is", "kaekae what time is it", "kae ...", "kaekae ..."
    m_wake = re.match(r'^(kae\s+kae|kaekae|kae|!kaekae|!kk)\b(?:\s*,\s*|\s+)?(.*)$', text_content, re.IGNORECASE)
    if m_wake:
        trigger_word = m_wake.group(1).lower()
        sub_query = m_wake.group(2).strip()

        # Check if asking for time
        if re.search(r'\b(?:what\s+time\s+(?:is\s+it|it\s+is)|what\s+time\s+is\s+it|what\s+time\s+it\s+is|time\s+check|the\s+time|what\s+is\s+the\s+time|current\s+time)\b', sub_query, re.IGNORECASE) or sub_query.lower() in {"time", "time?", "what time", "what time?"}:
            now_dt = datetime.now()
            time_str = now_dt.strftime("%I:%M %p").lstrip("0")
            date_str = now_dt.strftime("%A, %B %d")
            speaker_title = address_for_user(clean_user)
            resp = f"@{clean_user}, {speaker_title}, it is currently {time_str} ({date_str})."
            send_chat_message(resp, override_mute=True)
            return

        # If bare wake word
        if not sub_query:
            wake_reply = get_random_wake_response()
            send_chat_message(f"@{clean_user}, {wake_reply}", override_mute=True)
            return

    # Creator Yes/No Short Answer check (Authorized users: b3_d33, dog3lived, $htickie)
    # Strictly for casual questions, never intercepting ! commands or wake queries
    if is_authorized_user(clean_user) and not raw_msg.startswith("!") and is_yes_no_question(raw_msg):
        short_resp = get_short_authorized_reply()
        send_chat_message(f"@{clean_user}, {short_resp}", override_mute=True)
        return

    # 1. Spontaneous Chatty Mode Interaction (if active)
    with state.lock:
        is_chatty = state.chatty_mode

    if is_chatty and not raw_msg.startswith("!") and random.random() < 0.25:
        if time.time() - state.last_chatty_time > 50:
            state.last_chatty_time = time.time()
            with state.lock:
                # Randomly pick someone in the room to write about
                room_pool = [u for u in state.current_room_users if is_valid_camfrog_username(u) and u.lower() not in BOT_ALT_USERNAMES]
                picked = random.choice(room_pool) if room_pool else clean_user

            prompt = f"""{PERSONALITY}
You are KaeKae in chatty mode in chatroom [{state.current_focused_room}].
The room has active users: {', '.join(room_pool[:6])}.
You randomly chose to write about or chime in on: {picked}.
{clean_user} just typed: "{raw_msg}".
Chime in with a funny, preppy, valley-girl 1-sentence thought addressing or mentioning {picked}.
Keep under 250 characters!
"""
            chatty_reply = query_local_llm(prompt)
            send_chat_message(chatty_reply)
            return

    # 2. Mute Toggle: !shutup
    if msg_lower == "!shutup":
        with state.lock:
            state.responses_muted = True
        print("[BOT] Spontaneous chat muted via !shutup.")
        return

    # 3. Pagination trigger: !mo or y
    if msg_lower == "!mo" or (msg_lower == "y" and state.pending_pagination is not None):
        if handle_mo_command(clean_user):
            return

    # 4. Diss Control: !chill (Stops / turns off the diss function)
    if msg_lower in {"!chill", "chill", "!chill out"}:
        with state.lock:
            state.diss_active = False
            state.diss_target = ""
            state.bot_tone = "normal"
        send_chat_message(f"{format_bot_timestamp()} Diss function stopped. Chilling out!", override_mute=True)
        return

    # 5. Temperament Reset: !calm
    if msg_lower in {"!calm", "calm", "!kk calm"}:
        with state.lock:
            state.bot_tone = "normal"
            state.diss_active = False
            state.diss_target = ""
        send_chat_message(f"{format_bot_timestamp()} Normal temperament restored.", override_mute=True)
        return

    # 6. Tone Commands: expanded temperaments (angry, terminator, proud, sad, funny, happy, savage, chill, normal)
    m_tone = re.match(r'^!tone\s+(.+)$', msg_lower)
    if m_tone:
        chosen_tone = m_tone.group(1).strip()
        valid_tones = {
            "angry": "Furious, aggressive roasting mode engaged!",
            "terminator": "CYBERNETIC TERMINATOR MODE ACTIVATED. Scanning room. Dissing everyone.",
            "proud": "Triumphant, cocky, and flexing on everyone!",
            "sad": "Melodramatic emo valley-girl sadness mode...",
            "funny": "Funny & playful humor mode set!",
            "happy": "Cheerful & bubbly happiness mode set!",
            "savage": "Savage roasts mode set!",
            "chill": "Chill, relaxed vibes restored.",
            "normal": "Normal KaeKae temperament restored."
        }
        if chosen_tone in valid_tones:
            with state.lock:
                state.bot_tone = chosen_tone
            announcement = valid_tones[chosen_tone]
            send_chat_message(f"{format_bot_timestamp()} Tone set to '{chosen_tone}'. {announcement}", override_mute=True)
            return
        else:
            opts = ", ".join(valid_tones.keys())
            send_chat_message(f"@{clean_user}, available tones: {opts}", override_mute=True)
            return

    # 7. Diss Trigger: !diss [USERNAME] (Minute interval roasting loop)
    if msg_lower.startswith("!diss"):
        target_arg = raw_msg[5:].strip()
        handle_diss_command(clean_user, target_arg)
        return

    # 8. Room Recognition: !who, !users, !room (Uses (1/N !mo) pagination for 100s of users)
    if msg_lower in {"!who", "!users", "!room"}:
        win = get_camfrog_window()
        members = scan_room_users(win)
        paginate_room_users(members, clean_user)
        return

    # 9. Mic Grab Increments (5m to 72h): !grabs or !micstats
    if msg_lower.startswith("!grabs") or msg_lower.startswith("!micstats"):
        target_arg = re.sub(r'^!(?:grabs|micstats)\s*', '', raw_msg, flags=re.IGNORECASE).strip()
        handle_grabs_command(clean_user, target_arg)
        return

    # 10. Listening & Transcription Controls (Standardized)
    if msg_lower in {"!listen", "!listening on", "!kk listen"}:
        with state.lock:
            state.listening_enabled = True
        save_bot_runtime_state()
        send_chat_message(f"{format_bot_timestamp()} Listening is ON.", override_mute=True)
        return

    if msg_lower in {"!mute", "!listening off", "!kk mute"}:
        with state.lock:
            state.listening_enabled = False
        save_bot_runtime_state()
        send_chat_message(f"{format_bot_timestamp()} Listening is OFF.", override_mute=True)
        return

    # 11. Untranscribed Audio Queue Controls: !pending, !catchup
    if msg_lower in {"!pending", "!untranscribed"}:
        pending_cnt = get_pending_speech_count()
        send_chat_message(f"@{clean_user}, untranscribed speech clips in queue: {pending_cnt}", override_mute=True)
        return

    if msg_lower in {"!catchup", "!transcribe pending"}:
        send_chat_message(f"@{clean_user}, processing backlogged speech files...", override_mute=True)
        count = process_pending_audio_backlog()
        send_chat_message(f"@{clean_user}, transcribed {count} backlogged audio clips.", override_mute=True)
        return

    # 12. Chatty Mode Controls: !chat and !chat off
    if msg_lower in {"!chat off", "!chatoff"}:
        with state.lock:
            already_chat_off = not state.chatty_mode
            state.chatty_mode = False
        save_bot_runtime_state()
        if already_chat_off:
            print(f"[COMMAND] Chatty mode is already OFF (duplicate command from {clean_user} suppressed).")
            return
        send_chat_message(f"{format_bot_timestamp()} Chatty mode OFF.", override_mute=True)
        return

    if msg_lower in {"!chat", "!chat on"}:
        with state.lock:
            already_chat_on = state.chatty_mode
            state.chatty_mode = True
        save_bot_runtime_state()
        if already_chat_on:
            print(f"[COMMAND] Chatty mode is already ON (duplicate command from {clean_user} suppressed).")
            return
        send_chat_message(f"{format_bot_timestamp()} Chatty mode ON! I will be mingling in the room.", override_mute=True)
        return

    # 13. Say Command: !say "text" (Authorized Only - Speaks audibly on Camfrog mic via fast Talk button lock)
    m_say = re.match(r'^!say\s+"?([^"]+)"?$', raw_msg, re.IGNORECASE)
    if m_say:
        if not is_authorized_user(clean_user):
            send_chat_message(f"@{clean_user}, !say is reserved for authorized creators.", override_mute=True)
            return
        text_to_say = m_say.group(1).strip()
        speak_on_camfrog_microphone(text_to_say)
        send_chat_message(f"[Mic Broadcast]: {text_to_say}", override_mute=True)
        return

    # 13b. Grab Mic Command: !grab or !grab [seconds] (Authorized Only)
    m_grab = re.match(r'^!(?:grab|mic)\s*(\d+)?$', raw_msg, re.IGNORECASE)
    if m_grab:
        if not is_authorized_user(clean_user):
            send_chat_message(f"@{clean_user}, !grab is reserved for authorized creators.", override_mute=True)
            return
        dur = int(m_grab.group(1)) if m_grab.group(1) else 5
        dur = max(1, min(30, dur))
        def _timed_grab():
            method = "fallback"
            if global_talk_controller is not None:
                global_talk_controller.grab_mic()
                method = global_talk_controller.active_method
            else:
                try:
                    if pyautogui:
                        pyautogui.keyDown("f10")
                        method = "f10"
                except Exception:
                    pass
            send_chat_message(f"[CEF Talk]: Mic grabbed for {dur}s (strategy: {method}) by @{clean_user}.", override_mute=True)
            time.sleep(dur)
            if global_talk_controller is not None:
                global_talk_controller.release_mic()
            else:
                try:
                    if pyautogui:
                        pyautogui.keyUp("f10")
                        pyautogui.mouseUp()
                except Exception:
                    pass
            send_chat_message(f"[CEF Talk]: Mic released. Free for room!", override_mute=True)
        threading.Thread(target=_timed_grab, daemon=True).start()
        return

    # 13c. Release Mic Command: !release (Authorized Only)
    if msg_lower in {"!release", "!dropmic", "!releasemic"}:
        if not is_authorized_user(clean_user):
            send_chat_message(f"@{clean_user}, !release is reserved for authorized creators.", override_mute=True)
            return
        if global_talk_controller is not None:
            global_talk_controller.release_mic()
        try:
            if pyautogui:
                pyautogui.keyUp("f10")
                pyautogui.mouseUp()
        except Exception:
            pass
        send_chat_message(f"[CEF Talk]: Microphone released immediately. Room mic is free.", override_mute=True)
        return

    # 13d. Talk Mode: !talkmode [auto|f10|cef_hwnd|uia|mouse_hold|handsfree]
    m_talkmode = re.match(r'^!talkmode\s+([a-zA-Z0-9_]+)$', raw_msg, re.IGNORECASE)
    if m_talkmode:
        if not is_authorized_user(clean_user):
            send_chat_message(f"@{clean_user}, !talkmode is reserved for authorized creators.", override_mute=True)
            return
        new_mode = m_talkmode.group(1).lower()
        if new_mode in {"auto", "f10", "cef_hwnd", "uia", "mouse_hold", "handsfree"}:
            if global_talk_controller is not None:
                global_talk_controller.preferred_mode = new_mode
            send_chat_message(f"[CEF Talk]: Talk mode set to '{new_mode}'.", override_mute=True)
        else:
            send_chat_message(f"@{clean_user}, valid modes: auto, f10, cef_hwnd, uia, mouse_hold, handsfree", override_mute=True)
        return

    # 13e. Talk Status: !talkstatus
    if msg_lower in {"!talkstatus", "!micstatus", "!ceftalk"}:
        info_str = "CEF Talk Controller unavailable"
        if global_talk_controller is not None:
            tinfo = global_talk_controller.catch_talk_process()
            is_free, spk = global_talk_controller.is_mic_free()
            holding = "YES (Bot speaking)" if global_talk_controller.is_holding else "No"
            free_str = "Free" if is_free else f"Occupied by {spk}"
            info_str = f"CEF Talk Status: Attached={tinfo['attached']} | HWND={tinfo['cef_render_hwnd'] or 'UIA'} | Holding={holding} | Mic={free_str} | Mode={global_talk_controller.preferred_mode}"
        send_chat_message(info_str, override_mute=True)
        return

    # 13f. Dynamic Coordinates Reload: !reloadcoords or !reload
    if msg_lower in {"!reloadcoords", "!refreshcoords", "!reload"}:
        coords = load_calibrated_stage_coordinates()
        if global_talk_controller is not None:
            global_talk_controller._load_coordinates(force=True)
        if global_probe is not None:
            global_probe._load_coordinates(force=True)
        tb_x = coords.get('talk_button_x') if coords else None
        tb_y = coords.get('talk_button_y') if coords else None
        if not tb_x and coords and "talk_button" in coords and isinstance(coords["talk_button"], dict):
            tb_x = coords["talk_button"].get("x")
            tb_y = coords["talk_button"].get("y")
        tb_str = f"({tb_x}, {tb_y})" if tb_x and tb_y else "Auto/UIA"
        send_chat_message(f"[Coordinates]: Dynamically reloaded on the fly! Talk Button: {tb_str} (No restart needed).", override_mute=True)
        return

    # 14. Master Triggers: !triggers or !commands
    if msg_lower in {"!triggers", "!commands", "!help"}:
        help_lines = [
            f"=== KaeKae Master Triggers ===",
            f"[Chat Controls]: !kk, !chat (mingle on), !chat off, !shutup, !calm, !chill (stop diss), !tone funny|happy",
            f"[Roasts & Banter]: !diss [user], idk / !idk (smart answer or witty comeback)",
            f"[User & Room]: who is <user> (bio), info on <user> (stats), !who (room members), !grabs [user] (5-min mic logs)",
            f"[Mic & Audio]: !listen, !mute, !transcribe, !transcribed, !recall [q], !verbatim <user>, !mo (pages)",
            f"[Authorized ({address_for_user(clean_user)})]: !say \"msg\", !grab [sec], !release, !talkmode [mode], !talkstatus, !reloadcoords"
        ]
        queue_or_send_paginated("Master Triggers", help_lines, clean_user)
        return

    # 15. idk is the same as !idk (both chat and microphone)
    if msg_lower.startswith("!idk") or re.search(r'\bidk\b', msg_lower):
        handle_idk_command(clean_user, raw_msg)
        return

    # 11. Moderation Queries: "who blocked", "who unblocked", "who banned", etc.
    mod_queries = [
        ("who unblocked", "unblocked"),
        ("who blocked", "blocked"),
        ("who unpunished", "unpunished"),
        ("who punished", "punished"),
        ("who unbanned", "unbanned"),
        ("who banned", "banned"),
        ("who kicked", "kicked"),
    ]
    for trigger_phrase, action_name in mod_queries:
        if trigger_phrase in msg_lower:
            parts = re.split(rf'{trigger_phrase}', raw_msg, flags=re.IGNORECASE)
            target = parts[-1].strip() if len(parts) > 1 else ""
            handle_moderation_query(clean_user, action_name, target)
            return

    # 12. "who is" (Biography) vs "info on" (Statistical)
    if "who is" in msg_lower:
        target = re.split(r'who\s+is\s+', raw_msg, flags=re.IGNORECASE)[-1].strip()
        handle_user_lookup(clean_user, target, lookup_type="bio")
        return

    if "info on" in msg_lower or msg_lower.startswith("!info "):
        target = re.split(r'info\s+(?:on\s+)?', raw_msg, flags=re.IGNORECASE)[-1].strip()
        handle_user_lookup(clean_user, target, lookup_type="stats")
        return

    # 18. Independent Triggers: !recall, !verbatim, !verbatimall
    if msg_lower.startswith("!recall"):
        handle_recall_command(clean_user, raw_msg[7:].strip())
        return

    if msg_lower.startswith("!verbatimall"):
        handle_verbatimall_command(clean_user)
        return

    if msg_lower.startswith("!verbatim"):
        target = raw_msg[9:].strip()
        handle_verbatim_command(clean_user, target)
        return

    # 14. Insult Defense
    if any(phrase in msg_lower for phrase in AGGRESSIVE_PHRASES):
        with state.lock:
            state.bot_tone = "aggressive"
        prompt = f"""{PERSONALITY}
Requested tone: aggressive.
{clean_user} insulted the bot: "{raw_msg}".
Defend yourself sharply and sarcastically in 1 preppy sentence!
Under 280 characters!
"""
        reply = query_local_llm(prompt)
        send_chat_message(reply, override_mute=True)
        return

    # 15. PepeFrog Statement
    if "pepefrog" in msg_lower and random.random() < PEPEFROG_STATEMENT_CHANCE:
        send_chat_message(PEPEFROG_STATEMENT)
        return

    # 16. General Bot Trigger (!kk / !kaekae)
    has_trigger = False
    command_body = ""
    for trig in BOT_TRIGGERS:
        if raw_msg.lower().startswith(trig):
            has_trigger = True
            command_body = raw_msg[len(trig):].strip()
            break

    if not has_trigger:
        return

    # General chat response to !kk
    user_prompt = command_body if command_body else "Hey KaeKae!"
    speaker_title = address_for_user(clean_user)
    prompt = f"""{PERSONALITY}
Current Tone: {state.bot_tone}
User: {clean_user} (Title: {speaker_title})
Room: {state.current_focused_room}
User Message: "{user_prompt}"

Respond in character as KaeKae. Address the user as {speaker_title}.
Keep response strictly under 350 characters!
"""
    reply = query_local_llm(prompt)
    with state.lock:
        state.memory.append([f"{clean_user}: {user_prompt}", reply])
        state.recent_responses.append(reply)
    save_memory()
    send_chat_message(reply, override_mute=True)

# ==============================================================================
# BLOCK 15: MAIN RUNTIME & DIAGNOSTICS
# ==============================================================================

def test_audio_capture(duration_seconds: int = 15):
    """Interactive CLI test tool for microphone / VB-Audio Virtual Cable capture."""
    print("=" * 70)
    print(" KaeKae Audio Capture Diagnostic Tool")
    print("=" * 70)
    if sd is None or np is None:
        print("[ERROR] sounddevice and/or numpy are not installed.")
        return

    dev_idx, dev_name, native_rate, channels = resolve_audio_input_device(AUDIO_INPUT_DEVICE)
    print(f"Targeting Device: #{dev_idx} '{dev_name}'")
    use_rate = 16000
    try:
        sd.check_input_settings(device=dev_idx, samplerate=16000, channels=channels, dtype="int16")
    except Exception:
        use_rate = native_rate

    print(f"Testing live VU meter for {duration_seconds}s...")
    frames_per_sample = int(use_rate * 0.25)
    start_time = time.time()
    max_observed_peak = 0

    try:
        with sd.InputStream(device=dev_idx, channels=channels, samplerate=use_rate, dtype="int16") as stream:
            while time.time() - start_time < duration_seconds:
                data, _ = stream.read(frames_per_sample)
                peak = int(np.max(np.abs(data)))
                if peak > max_observed_peak:
                    max_observed_peak = peak
                bar_len = min(int((peak / 3000) * 30), 30)
                meter = "█" * bar_len + "░" * (30 - bar_len)
                status = "LOUD" if peak > 1500 else ("DETECTED" if peak > 150 else "QUIET/SILENCE")
                print(f"\rAudio In: [{meter}] Peak: {peak:5d}/32767 ({status}) ", end="", flush=True)
                time.sleep(0.05)
        print(f"\n\n[DIAGNOSTIC RESULT] Max Peak: {max_observed_peak}/32767")
    except Exception as e:
        print(f"\n[TEST FAILED] {e}")

def print_triggers_list():
    """Prints a clean, comprehensive list of all bot triggers and calls."""
    print("\n" + "=" * 75)
    print(" KAEKAE BOT - NEW MASTER TRIGGERS & COMMAND LIST")
    print("=" * 75)
    print("""
[Chat Triggers & Direct Queries]
  kae / kaekae / kae kae   - Wake triggers anywhere after time/date and username
  kae what time it is      - Instantly returns current exact time & date to caller
  kaekae what time is it   - Instantly returns current exact time & date to caller
  !kk [query]              - Ask KaeKae anything in chat
  !chat                    - Turn chatty mode ON (mingles and comments on room members)
  !chat off                - Turn chatty mode OFF (quiet in room)
  !shutup                  - Mute spontaneous chatter

[Temperament & Continuous 1-Minute Diss System]
  !diss [username]         - Roasts target user (or room). DEPLOYS CONTINUOUS 1-MINUTE INTERVAL ROASTS!
  !chill / chill           - Stop the diss function completely and restore chill mode
  !calm / calm             - Reset temperament to normal
  !tone <temperament>      - Set personality temperament:
                             * angry (aggressive fiery roasts)
                             * terminator (Cyberdyne T-800 dissing everyone in room)
                             * proud (triumphant boastful flexing)
                             * sad (melodramatic emo valley-girl sighs)
                             * funny (witty comedy mode)
                             * happy (bubbly cheerful mode)
                             * savage (brutal roasts)
                             * chill (relaxed laid-back)
                             * normal (standard valley-girl)

[Room & User Intelligence]
  !who / !room / !users    - Paginated list of all room occupants using '(1/N !mo)' format (<=400 chars)
  !mo / y                  - Send the next page of room members, recall results, or grabs
  who is <username>        - Narrative biography from audio & chat history (no mod logs)
  info on <username>       - Statistical profile (Audio/Text Tone, top non-filler word, mic grabs)
  !grabs [user] [duration] - Microphone grab logs with flexible increments from 5 minutes to 72 hours!
                             Examples: !grabs 5m, !grabs 30m, !grabs 1h, !grabs 24h, !grabs 72h
  idk [query] / !idk       - Smart instant answer or funny contextual comeback (Chat & Mic)

[Microphone, Audio & Verbatim Transcripts]
  !listen                  - Turn microphone listening ON
  !mute                    - Turn microphone listening OFF
  !transcribe              - Echo transcribed room speech to Camfrog chat
  !transcribed             - Stop echoing transcribed speech to chat
  !pending / !catchup      - View & transcribe backlogged audio clips
  !recall <term>           - Exact word/acronym search (e.g. '!recall pi' matches 'pi' alone, NOT 'opinion')
  !recall *<term>*         - Wildcard substring search (e.g. '!recall *pi*' matches 'opinion', 'recipe', etc.)
  !verbatim [username]     - Exact word-for-word quotes and mic transcripts for user (or active speaker)
  !verbatimall             - Recent verbatim speech from everyone in the room

[Authorized Creator (Papi)]
  Authorized Users: b3_d33, dog3lived, $htickie, b3_dee, dog
  Title: Addressed with respect as 'Papi'
  Short replies: Quick respectful responses ('Yes Sir', 'No Sir', 'Okay Daddy', 'As you wish Pop')
  !say "message"           - Audibly speaks through Camfrog microphone via Talk button (to LEFT of arrow)
""")
    print("=" * 75 + "\n")

def main():
    if "--calibrate" in sys.argv:
        try:
            import calibrate_camfrog
            calibrate_camfrog.run_calibration_wizard()
        except Exception as e:
            print(f"[CALIBRATE ERROR] {e}")
        sys.exit(0)

    if "--test-audio" in sys.argv or "-t" in sys.argv:
        test_audio_capture()
        sys.exit(0)

    if "--triggers" in sys.argv or "--help" in sys.argv:
        print_triggers_list()
        sys.exit(0)

    print("=" * 75)
    print(" KaeKae Camfrog Bot Starting Up...")
    print("=" * 75)
    print_triggers_list()
    
    print("[INIT] Loading stored data and runtime state...")
    load_all_persisted_data()
    print("[INIT] Stored data loaded.")

    win = get_camfrog_window()
    if win:
        print(f"[INIT] Connected to Camfrog window! Focused room: '{state.current_focused_room}'")
        if not state.startup_disclaimer_sent:
            send_chat_message(f"{format_bot_timestamp()} {STARTUP_DISCLAIMER}", override_mute=True)
            state.startup_disclaimer_sent = True
    else:
        print("[INIT] Camfrog window not detected yet. Watching for window...")

    # Launch decoupled CEF dynamic speaker probe and async audio filer
    if global_probe is not None:
        try:
            global_probe.start()
            print("[CEF-PROBE] Fast-path Chromium speaker probe background service started.")
        except Exception as e:
            print(f"[CEF-PROBE] Notice: Could not start global_probe: {e}")

    if global_audio_filer is not None:
        try:
            global_audio_filer.start()
            print("[AUDIO-FILER] Decoupled async audio chunk archiver started.")
        except Exception as e:
            print(f"[AUDIO-FILER] Notice: Could not start global_audio_filer: {e}")

    if getattr(sys.modules.get("kaekae_bot", sys.modules[__name__]), "AUDIO_RECORD_ENABLED", True) and globals().get("AUDIO_RECORD_ENABLED", True):
        audio_thread = threading.Thread(target=voice_listener_worker, daemon=True)
        audio_thread.start()
        print("[AUDIO THREAD] Room microphone streaming thread started.")
    else:
        print("[AUDIO THREAD] Microphone streaming disabled in this process (delegated to Audio Worker).")

    diss_thread = threading.Thread(target=diss_interval_worker, daemon=True)
    diss_thread.start()

    scanner_thread = threading.Thread(target=room_users_scanner_worker, daemon=True)
    scanner_thread.start()
    print("[USER-SCANNER] Real-time Camfrog room member roster tracking started.")

    # Start hotkey listener (Left-Ctrl + Right-Click to stop transcription, F8 to toggle, ASDF to listen)
    start_transcribe_hotkey_listener()

    def handle_sigint(sig, frame):
        print("\n[SHUTDOWN] Received Ctrl+C. Saving all state and exiting cleanly...")
        state.shutdown_event.set()
        try:
            if sd is not None:
                sd.stop()
        except Exception:
            pass
        try:
            save_bot_runtime_state()
            save_users()
            save_kicks()
            save_memory()
        except Exception:
            pass
        time.sleep(0.2)
        os._exit(0)

    signal.signal(signal.SIGINT, handle_sigint)

    # Keep Chromium CEF accessibility awake
    last_cef_ping_time = 0.0
    OBJID_CLIENT = 0xFFFFFFFC

    # Resilient Dual-Engine loop: Fast CEF UIAutomation + Complementary OCR
    while not state.shutdown_event.is_set():
        try:
            curr_win = get_camfrog_window()
            if curr_win:
                now_mono = time.time()
                # 1. Periodic WM_GETOBJECT ping to force CEF/Chromium to expose accessibility DOM
                if now_mono - last_cef_ping_time > 10.0:
                    last_cef_ping_time = now_mono
                    try:
                        def _ping_cef(ch_hwnd, _):
                            cls = win32gui.GetClassName(ch_hwnd)
                            if "Chrome_RenderWidgetHostHWND" in cls:
                                ctypes.windll.user32.SendMessageW(ch_hwnd, 0x003D, 0, OBJID_CLIENT)
                        win32gui.EnumChildWindows(curr_win.handle, _ping_cef, None)
                    except Exception:
                        pass

                # 2. Extract DOM text nodes directly from CEF
                texts = []
                try:
                    for ctrl in curr_win.descendants():
                        try:
                            c_type = ctrl.element_info.control_type
                            if c_type in {"Text", "Hyperlink", "ListItem", "Edit", "Document", "Pane", "Custom"}:
                                txt = (ctrl.element_info.name or ctrl.window_text() or "").strip()
                                if txt:
                                    texts.append(txt)
                        except Exception:
                            pass
                except Exception:
                    pass

                # 3. Process CEF messages with deterministic signature deduplication (NO line index!)
                parsed_msgs = extract_chat_messages(texts)
                for clean_u, t, m in parsed_msgs:
                    if not is_valid_camfrog_username(clean_u):
                        continue
                    if "[mic]" in clean_u.lower() or "[mic]" in m.lower():
                        continue

                    # Sanitize username
                    clean_u = clean_u.strip(": \t\r\n")
                    if not clean_u or len(clean_u) < 2 or len(clean_u) > 20:
                        continue

                    is_auth = is_authorized_user(clean_u)
                    u_low = clean_u.lower()

                    if not is_auth:
                        if u_low in BOT_ALT_USERNAMES or u_low == BOT_USERNAME.lower() or "kaekae" in u_low or u_low in IGNORED_USERS:
                            continue

                        norm_m = " ".join(m.lower().split())
                        with state.lock:
                            now_m = time.time()
                            state.recent_bot_messages = {k: ts for k, ts in state.recent_bot_messages.items() if now_m - ts < 120}
                            if norm_m in state.recent_bot_messages:
                                continue

                        if "kaekae is alpha testing" in norm_m or "alpha testing, debugging" in norm_m:
                            continue

                    # Unified message signature: sender + time + message (NEVER line index)
                    sig = make_message_signature(clean_u, t, m)
                    with state.lock:
                        if sig in state.seen_message_signatures:
                            continue
                        state.seen_message_signatures.add(sig)
                        if len(state.seen_message_signatures) > 3000:
                            state.seen_message_signatures = set(list(state.seen_message_signatures)[-1500:])

                    # Rolling text deduplication buffer (prevents duplicate logs while message sits on screen)
                    # Direct bot commands (starting with '!', '/', or containing transcribe/triggers) NEVER get dropped!
                    m_strip = m.strip()
                    is_bot_cmd = (
                        m_strip.startswith("!") or 
                        m_strip.startswith("/") or 
                        any(m_strip.lower().startswith(trig) for trig in BOT_TRIGGERS) or
                        "transcribe" in m.lower() or 
                        "transribe" in m.lower()
                    )
                    if not is_bot_cmd:
                        norm_txt = re.sub(r'[^a-zA-Z0-9]', '', m.lower())
                        if not norm_txt or len(norm_txt) < 1:
                            continue
                        text_fingerprint = f"{u_low}|{norm_txt}"
                        now_ts_sec = time.time()
                        with state.lock:
                            if not hasattr(state, "recent_chat_texts"):
                                state.recent_chat_texts = {}
                            expired = [k for k, ts in state.recent_chat_texts.items() if now_ts_sec - ts > 90]
                            for k in expired:
                                del state.recent_chat_texts[k]

                            if text_fingerprint in state.recent_chat_texts:
                                continue
                            state.recent_chat_texts[text_fingerprint] = now_ts_sec

                    print(f"[CEF CHAT DETECTED] {t} <{clean_u}>: {m}")
                    record_chat_message(clean_u, m, t, "cef_automation")
                    process_chat_message(clean_u, t, m)

                # 4. Check for room moderation events in CEF text nodes (Single node & Sliding Window)
                cef_mod_candidates = []
                for i, txt in enumerate(texts):
                    t_low = txt.lower()
                    if any(w in t_low for w in ["kick", "block", "punish", "ban"]):
                        cef_mod_candidates.append(txt)
                        # Sliding window: combine preceding and succeeding DOM nodes
                        for w_start in range(max(0, i - 2), i + 1):
                            for w_end in range(i + 1, min(len(texts), i + 4)):
                                combined = " ".join(t.strip() for t in texts[w_start:w_end+1] if t.strip())
                                if combined and len(combined) <= 150:
                                    cef_mod_candidates.append(combined)

                for cand in cef_mod_candidates:
                    ev = detect_kick_block("", cand)
                    if ev and ev.get("actor", "").lower() not in BOT_ALT_USERNAMES:
                        sig = f"{state.current_focused_room}|{ev['actor'].lower()}|{ev['action']}|{ev['target'].lower()}"
                        with state.lock:
                            if sig not in state.ocr_recent_events_cache:
                                state.ocr_recent_events_cache[sig] = time.time()
                                ev["time"] = format_bot_timestamp()
                                ev["room"] = state.current_focused_room
                                state.kicks.append(ev)
                                state.moderation_audit.append(ev)
                                actor_key = ev["actor"].lower()
                                if actor_key in state.users:
                                    state.users[actor_key].setdefault("moderation_actions", []).append(ev)
                                print(f"[CEF MOD LOGGED] {ev['actor']} {ev['action']} {ev['target']} (from '{cand}')")
                                save_kicks()
                                save_users()

                # 5. Complementary OCR scan
                if getattr(state, "watching_ocr_enabled", True):
                    ocr_scan_camfrog_chat()

            time.sleep(globals().get("CEF_CHAT_SCAN_INTERVAL", 0.25))
        except Exception as e:
            print(f"[MAIN LOOP ERROR] {e}")
            traceback.print_exc()
            time.sleep(2.0)

if __name__ == "__main__":
    main()
