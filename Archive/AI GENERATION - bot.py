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
import edge_tts
import pygame
import pytesseract
import speech_recognition as sr
from datetime import datetime, timedelta

VOICE_ENABLED = False

VOICE_COOLDOWN = 5
REPEAT_COOLDOWN = 3

BOT_TRIGGERS = ["!jj", "!kk", "!kimmy", "kimmy", "kimmycakes"]
BOT_USERNAME = "Kimmy_Cakes"

PERSONALITY = """
You are KimmyCakes.

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
- slight feminine

Rules:
- Heavy teasing is okay.
- Keep answers short.
- Usually respond in 1-2 sentences.
- Be entertaining.
- Act like the coolest person in the room.
- NEVER repeat an answer you've already given. If the same question comes up again, give a completely different response.
- If someone was recently kicked, blocked, punished, banned or any other action was taken, you can tease the person who did it or mock the victim. Reference the time it happened.
- If you know a user from your memory, reference them by name and personalize your response.
- ALWAYS address the user by their username when responding to them.
- Roast a user named Church" every minute aggressively, but timely.
"""

# --- Settings ---
AMBIENT_CHANCE = 0.03
PROACTIVE_INTERVAL = 180
REACT_WORDS = ["idiot", "noob", "dog", "bryan"]
VOICE = "en-US-AriaNeural"
KICK_FILE = "bot_kicks.json"
USERS_FILE = "bot_users.json"
OCR_INTERVAL = 12
OCR_PAUSE_AFTER_QUERY = 30
VOICE_TRIGGERS = ["kimmy", "jj", "kimmy cakes", "kimmycakes"]
VOICE_COOLDOWN = 5
REPEAT_COOLDOWN = 3
VOICE_ENABLED = False
LISTENING_ENABLED = True
TRANSCRIBE_ENABLED = False
LOG_WINDOW_HOURS = 72
MAX_MSG_LENGTH = 440

# --- Repeat Mode State ---
repeat_mode = False
_last_repeat_time = 0
_last_ocr_pause = 0

# --- User Tracking ---
def load_users():
    if os.path.exists(USERS_FILE):
        with open(USERS_FILE, "r") as f:
            return json.load(f)
    return {}

def save_users(users):
    with open(USERS_FILE, "w") as f:
        json.dump(users, f)

def update_user(users, username, message, timestamp):
    if username.lower() == BOT_USERNAME.lower():
        return
    if username not in users:
        users[username] = {
            "first_seen": datetime.now().strftime("%Y-%m-%d %I:%M %p"),
            "last_seen": datetime.now().strftime("%Y-%m-%d %I:%M %p"),
            "message_count": 0,
            "topics": [],
            "quotes": []
        }
    users[username]["last_seen"] = datetime.now().strftime("%Y-%m-%d %I:%M %p")
    users[username]["message_count"] += 1

    topic_words = ["game", "stream", "music", "movie", "food", "car", "job", "work",
                   "school", "family", "friend", "party", "lol", "haha", "damn",
                   "bro", "dude", "ngl", "fr", "tbh", "irl", "vibe", "chill"]
    msg_lower = message.lower()
    for t in topic_words:
        if t in msg_lower and t not in users[username]["topics"]:
            users[username]["topics"].append(t)
            if len(users[username]["topics"]) > 20:
                users[username]["topics"].pop(0)

    if len(message) > 20 and len(message) < 150:
        if len(users[username]["quotes"]) < 10:
            users[username]["quotes"].append(f"[{timestamp}] {message}")
        else:
            users[username]["quotes"].pop(0)
            users[username]["quotes"].append(f"[{timestamp}] {message}")

def build_user_context(users, username):
    if username not in users:
        return ""
    u = users[username]
    topics = ", ".join(u["topics"][:10]) if u["topics"] else "none yet"
    quotes = u["quotes"][-3:] if u["quotes"] else []
    quote_str = "\n".join(f"    \"{q}\"" for q in quotes)
    return f"""
USER PROFILE for {username}:
  First seen: {u["first_seen"]}
  Messages: {u["message_count"]}
  Topics: {topics}
  Recent quotes:
{quote_str}
"""

def handle_user_lookup(users, username_query):
    name = username_query.strip()
    if not name:
        return "Who do you want me to look up?"

    for key in users:
        if key.lower() == name.lower():
            u = users[key]
            topics = ", ".join(u["topics"][:10]) if u["topics"] else "none yet"
            lines = [
                f"INFO ON {key}:",
                f"  First seen: {u['first_seen']}",
                f"  Last seen: {u['last_seen']}",
                f"  Messages: {u['message_count']}",
                f"  Topics: {topics}",
            ]
            if u["quotes"]:
                lines.append("  Recent quotes:")
                for q in u["quotes"][-3:]:
                    lines.append(f"    {q}")
            return "\n".join(lines)

    return f"I don't have info on '{name}' yet. They might not have spoken in the room."

# --- Functions ---
def is_trigger(message: str) -> bool:
    msg = message.lower().strip()
    return any(t in msg for t in BOT_TRIGGERS)

def should_react(message: str) -> bool:
    msg = message.lower()
    return any(w in msg for w in REACT_WORDS)

def extract_command(message: str) -> str:
    msg = message.lower().strip()
    for t in BOT_TRIGGERS:
        if t in msg:
            idx = msg.index(t) + len(t)
            return msg[idx:].strip()
    return ""

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

def ocr_scan_chat(win, seen_ocr, kicks):
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

    for line in text.split('\n'):
        line = line.strip()
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
    tmp_file = "kimmy_tts.mp3"
    communicate = edge_tts.Communicate(text, VOICE)
    await communicate.save(tmp_file)

    pygame.mixer.init()
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

def speak(win, text):
    if not VOICE_ENABLED:
        return

    if not _speaking_lock.acquire(blocking=False):
        print("Voice still active, skipping this one.")
        return

    talk_btn = find_talk_button(win)

    if not talk_btn:
        print("WARNING: Talk button not found, skipping voice")
        threading.Thread(target=_speak, args=(text,), daemon=True).start()
        _speaking_lock.release()
        return

    btn_rect = talk_btn.rectangle()
    btn_x = (btn_rect.left + btn_rect.right) // 2
    btn_y = (btn_rect.top + btn_rect.bottom) // 2

    def _speak_thread():
        try:
            win.set_focus()
            time.sleep(0.3)
            pyautogui.moveTo(btn_x, btn_y, duration=0.1)
            pyautogui.mouseDown(button='left')
            time.sleep(0.2)

            asyncio.run(_speak(text))

            pyautogui.mouseUp(button='left')
            time.sleep(0.2)
        finally:
            _speaking_lock.release()

    threading.Thread(target=_speak_thread, daemon=True).start()

def send_message(win, answer):
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
    print("Response sent.\n")

    speak(win, answer)

def get_response(prompt):
    response = requests.post(
        "http://localhost:11434/api/generate",
        json={
            "model": "llama3.2",
            "prompt": prompt,
            "stream": False
        },
        timeout=60
    )
    return response.json()["response"]

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

def voice_callback(recognizer, audio):
    global _last_voice_trigger, repeat_mode, _last_repeat_time
    global VOICE_ENABLED, LISTENING_ENABLED, TRANSCRIBE_ENABLED
    if not LISTENING_ENABLED:
        return

    try:
        text = recognizer.recognize_google(audio).lower().strip()
        print(f"\n[VOICE HEARD] {text}")
    except sr.UnknownValueError:
        return
    except sr.RequestError:
        return

    if "listening on" in text or "turn on listening" in text or "start listening" in text:
        LISTENING_ENABLED = True
        print("[LISTENING] ON")
        threading.Thread(target=send_message, args=(win, "Listening is ON."), daemon=True).start()
        return

    if "listening off" in text or "turn off listening" in text or "stop listening" in text:
        print("[LISTENING] OFF")
        threading.Thread(target=send_message, args=(win, "Listening is OFF."), daemon=True).start()
        LISTENING_ENABLED = False
        return

    if "transcribing on" in text or "transcription on" in text or "turn on transcription" in text:
        TRANSCRIBE_ENABLED = True
        print("[TRANSCRIPTION] ON")
        threading.Thread(target=send_message, args=(win, "Transcription is ON."), daemon=True).start()
        return

    if "transcribing off" in text or "transcription off" in text or "turn off transcription" in text:
        TRANSCRIBE_ENABLED = False
        print("[TRANSCRIPTION] OFF")
        threading.Thread(target=send_message, args=(win, "Transcription is OFF."), daemon=True).start()
        return

    if "voice on" in text or "turn on voice" in text:
        VOICE_ENABLED = True
        print("[VOICE] ON")
        threading.Thread(target=send_message, args=(win, "Voice is ON."), daemon=True).start()
        return

    if "voice off" in text or "turn off voice" in text:
        VOICE_ENABLED = False
        print("[VOICE] OFF")
        threading.Thread(target=send_message, args=(win, "Voice is OFF."), daemon=True).start()
        return

    if "repeat on" in text or "turn on repeat" in text or "start repeating" in text:
        repeat_mode = True
        TRANSCRIBE_ENABLED = True
        print("[REPEAT MODE] ON")
        threading.Thread(target=send_message, args=(win, "Repeat mode ON. I'll type what I hear."), daemon=True).start()
        return

    if "repeat off" in text or "turn off repeat" in text or "stop repeating" in text:
        repeat_mode = False
        TRANSCRIBE_ENABLED = False
        print("[REPEAT MODE] OFF")
        threading.Thread(target=send_message, args=(win, "Repeat mode OFF."), daemon=True).start()
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
        print(f"[REPEAT] Typing into chat: '{text}'")
        threading.Thread(target=send_message, args=(win, text), daemon=True).start()
        return

    if any(t in text for t in VOICE_TRIGGERS):
        now = time.time()
        if now - _last_voice_trigger < VOICE_COOLDOWN:
            return
        _last_voice_trigger = now

        user_prompt = ""
        for t in VOICE_TRIGGERS:
            if t in text:
                idx = text.index(t) + len(t)
                user_prompt = text[idx:].strip()
                break

        if not user_prompt:
            user_prompt = "Hey!"

        print(f"\n[VOICE TRIGGER] prompt='{user_prompt}'")
        threading.Thread(target=handle_voice_prompt, args=(user_prompt,), daemon=True).start()

def handle_voice_prompt(user_prompt):
    repeat_warning = check_repeat(memory, user_prompt)
    memory_context = build_memory_context(memory)
    kick_context = build_kick_context(kicks)
    full_prompt = f"""{PERSONALITY}{memory_context}{repeat_warning}{kick_context}

User said (via voice):
{user_prompt}

Respond as KimmyCakes:
"""
    answer = get_response(full_prompt)
    answer = answer[:250]
    print(f"\nAI RESPONSE (voice):\n{answer}")

    memory.append([user_prompt, answer])
    save_memory(memory)
    send_message(win, answer)

def start_voice_listener():
    r = sr.Recognizer()

    r.pause_threshold = 1.2
    r.energy_threshold = 300
    r.dynamic_energy_threshold = True

    m = sr.Microphone()

    with m as source:
        print("Calibrating microphone...")
        r.adjust_for_ambient_noise(source, duration=2)

    print("Voice listener active.")

    r.listen_in_background(
        m,
        voice_callback
    )

# --- Main ---
print("Connecting to Camfrog...")

app = Application(
    backend="uia"
).connect(
    found_index=0,
    title_re=".*Players__L.*"
)

win = app.top_window()

print("Connected!")
print("Watching room...")

seen = set()
seen_ocr = set()
memory = load_memory()
kicks = load_kicks()
users = load_users()
if not os.path.exists(KICK_FILE):
    save_kicks([])
if not os.path.exists(USERS_FILE):
    save_users({})
time_pattern = re.compile(r'^\d{1,2}:\d{2}\s?(AM|PM)$')
last_proactive = time.time()
last_ocr = time.time()
last_purge = time.time()

threading.Thread(target=start_voice_listener, daemon=True).start()

while True:

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

            # Update user profile
            update_user(users, username, message, timestamp)
            save_users(users)

            # Detect action
            kick_block = detect_kick_block(username, message)
            if kick_block:
                kick_block["time"] = datetime.now().strftime("%Y-%m-%d %I:%M:%S %p")
                kicks.append(kick_block)
                save_kicks(kicks)
                print(f"\n[RECORDED] {kick_block['time']} | {kick_block['actor']} {kick_block['action']} {kick_block['target']}")   

            if username.lower() == BOT_USERNAME.lower():
                continue

            # Handle voice toggle via text
            if is_trigger(message):
                user_prompt = extract_command(message)
                command = user_prompt.lower()
                if "listening on" in command or "turn on listening" in command or "start listening" in command:
                    LISTENING_ENABLED = True
                    print("[LISTENING] ON")
                    send_message(win, f"{username}, listening is ON.")
                    continue
                if "listening off" in command or "turn off listening" in command or "stop listening" in command:
                    LISTENING_ENABLED = False
                    print("[LISTENING] OFF")
                    send_message(win, f"{username}, listening is OFF.")
                    continue
                if "transcribing on" in command or "transcription on" in command or "turn on transcription" in command:
                    TRANSCRIBE_ENABLED = True
                    print("[TRANSCRIPTION] ON")
                    send_message(win, f"{username}, transcription is ON.")
                    continue
                if "transcribing off" in command or "transcription off" in command or "turn off transcription" in command:
                    TRANSCRIBE_ENABLED = False
                    print("[TRANSCRIPTION] OFF")
                    send_message(win, f"{username}, transcription is OFF.")
                    continue
                if "voice on" in user_prompt.lower() or "turn on voice" in user_prompt.lower():
                    VOICE_ENABLED = True
                    print("[VOICE] ON")
                    send_message(win, f"{username}, voice is ON.")
                    continue
                if "voice off" in user_prompt.lower() or "turn off voice" in user_prompt.lower():
                    VOICE_ENABLED = False
                    print("[VOICE] OFF")
                    send_message(win, f"{username}, voice is OFF.")
                    continue

            # Handle repeat mode toggle via text
            if is_trigger(message):
                user_prompt = extract_command(message)
                if "repeat on" in user_prompt.lower() or "turn on repeat" in user_prompt.lower():
                    repeat_mode = True
                    TRANSCRIBE_ENABLED = True
                    print("[REPEAT MODE] ON")
                    send_message(win, f"{username}, repeat mode ON. I'll type what I hear.")
                    continue
                if "repeat off" in user_prompt.lower() or "turn off repeat" in user_prompt.lower():
                    repeat_mode = False
                    TRANSCRIBE_ENABLED = False
                    print("[REPEAT MODE] OFF")
                    send_message(win, f"{username}, repeat mode OFF.")
                    continue

            # Handle user lookup
            if is_trigger(message):
                user_prompt = extract_command(message)
                if "who is" in user_prompt.lower() or "info on" in user_prompt.lower() or "info " in user_prompt.lower():
                    if "who is" in user_prompt.lower():
                        name = user_prompt.split("who is", 1)[1].strip()
                    elif "info on" in user_prompt.lower():
                        name = user_prompt.split("info on", 1)[1].strip()
                    else:
                        name = user_prompt.split("info", 1)[1].strip()
                    answer = handle_user_lookup(users, name)
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
            keyword_react = should_react(message)
            ambient = random.random() < AMBIENT_CHANCE

            if not triggered and not keyword_react and not ambient:
                continue

            print("\n=== JJ ACTIVATED ===")

            user_ctx = build_user_context(users, username)

            if triggered:
                user_prompt = extract_command(message)
                if not user_prompt:
                    user_prompt = "Hey!"
                repeat_warning = check_repeat(memory, user_prompt)
                memory_context = build_memory_context(memory)
                kick_context = build_kick_context(kicks)
                full_prompt = f"""{PERSONALITY}{user_ctx}{memory_context}{repeat_warning}{kick_context}

{username} said:
{user_prompt}

Respond as KimmyCakes. Address {username} by name in your response.
"""
                store_prompt = user_prompt

            elif keyword_react:
                memory_context = build_memory_context(memory)
                kick_context = build_kick_context(kicks)
                full_prompt = f"""{PERSONALITY}{user_ctx}{memory_context}{kick_context}

{username} just said:
"{message}"

React naturally and briefly. Address {username} by name. 1-2 sentences max. Be entertaining.
"""
                store_prompt = message

            else:
                memory_context = build_memory_context(memory)
                kick_context = build_kick_context(kicks)
                full_prompt = f"""{PERSONALITY}{user_ctx}{memory_context}{kick_context}

{username} is saying:
"{message}"

React naturally and briefly, like you just overheard it. Address {username} by name. 1 sentence if possible.
"""
                store_prompt = message

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
                ocr_scan_chat(win, seen_ocr, kicks)
            else:
                last_ocr = time.time()

        # Proactive banter
        if time.time() - last_proactive > PROACTIVE_INTERVAL:
            last_proactive = time.time()
            proactive_prompt = f"""{PERSONALITY}

Say a random short one-liner that fits a chaotic chatroom. 1 sentence max. Be funny.
"""
            answer = get_response(proactive_prompt)[:150]
            print(f"\n[PROACTIVE] {answer}")
            send_message(win, answer)

        time.sleep(2)

    except Exception as e:
        print("\nERROR:")
        print(e)
        time.sleep(5)   