"""Runtime configuration for the UI-Automation Camfrog bot.

This release intentionally has no screen-capture or OCR dependencies. Camfrog
must expose the relevant controls through Windows UI Automation for a value to
be read; an unavailable control is reported as unavailable rather than guessed.
"""

from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent
DATA_DIR = PROJECT_ROOT / "data"
LOG_DIR = PROJECT_ROOT / "logs"
SUPPRESSED_DATA_DIR = DATA_DIR / "suppressed"
DATABASE_PATH = DATA_DIR / "camfrog_bot.db"

# UI Automation is the only capture source in this version.
CAPTURE_BACKEND = "uia"
OCR_ENABLED = False
DXCAM_ENABLED = False
TESSERACT_ENABLED = False
IMAGE_CAPTURE_ENABLED = False

# More specific pattern based on your window properties
CAMFROG_WINDOW_TITLE_RE = r"(?i).*Players__Lounge([,:].*?)?\s*Video Chat Room.*"
POLL_INTERVAL_SECONDS = 0.75
UIA_CACHE_SECONDS = 0.30
MAX_CHAT_MESSAGE_LENGTH = 425
CHAT_HISTORY_LIMIT = 10

# Tab positions for room switching (x, y, width, height)
ROOM_TAB_POSITIONS = {
    "Room List": [1313, 37, 1473, 71],
    "Players__Lounge": [1473, 37, 1633, 71],
    "Drama_Central": [1633, 37, 1793, 71]
}

BOT_SETTINGS = {
    "chat_mode": False,
    "silent_mode": False,
    "transcription_mode": False,  # Reserved; no speech capture in this release.
    "running": True,
}

# Leave this empty to prevent native moderation commands from being sent. Add
# normalized Camfrog usernames only after the bot account has moderator rights.
MODERATION_ALLOWED_SENDERS: set[str] = set()
NATIVE_MODERATION_COMMANDS = {"unpunish", "unblockmic", "unban", "topic", "watchlist"}

TRIGGER_NAMES = (
    "kaekae", "!chat", "!chatoff", "!shutup", "!transcribe", "!transcribed",
    "!suppress", "!unsuppress", "!say", "!diss", "!who is", "!info on",
    "!grabs", "-", "!idk", "who kicked/blocked/banned/punished", "!happy",
    "!sad", "!mad", "!triggers",
)
