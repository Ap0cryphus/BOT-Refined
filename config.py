"""Runtime configuration for the UI-Automation Camfrog bot with VB-Cable TTS."""

from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent
DATA_DIR = PROJECT_ROOT / "data"
LOG_DIR = PROJECT_ROOT / "logs"
SUPPRESSED_DATA_DIR = DATA_DIR / "suppressed"
DATABASE_PATH = DATA_DIR / "camfrog_bot.db"

CAPTURE_BACKEND = "uia"
OCR_ENABLED = False
DXCAM_ENABLED = False
TESSERACT_ENABLED = False
IMAGE_CAPTURE_ENABLED = False

# Window title can change dynamically when room topic changes.
CAMFROG_WINDOW_TITLE_RE = r"(?i).*(Players__Lounge|Drama_Central|Camfrog|Video Chat Room).*"
POLL_INTERVAL_SECONDS = 0.75
UIA_CACHE_SECONDS = 0.30
MAX_CHAT_MESSAGE_LENGTH = 425
CHAT_HISTORY_LIMIT = 10

# Fixed tab click coordinates (x, y) and bounding boxes [left, top, right, bottom]
ROOM_TAB_CLICK_POINTS = {
    "Room List": (1390, 50),
    "Players__Lounge": (1550, 50),
}

ROOM_TAB_POSITIONS = {
    "Room List": [1313, 37, 1473, 71],
    "Players__Lounge": [1473, 37, 1633, 71],
    "Drama_Central": [1633, 37, 1793, 71],
}

# Exact calibrated BoundingRectangles [left, top, right, bottom]
CHAT_WINDOW_RECT = (1281, 170, 2299, 1160)      # ControlType Pane(50033)
TALK_BUTTON_RECT = (1291, 1169, 1361, 1195)     # ControlType Button(50000)
USER_LIST_RECT = (2303, 141, 2559, 1160)        # ControlType List(50008), items at r=2559

# Specific ListItem(50007) rectangles inside User List to ignore (headers/separators)
IGNORED_USER_LIST_RECTS = {
    (2303, 141, 2559, 163),
    (2303, 207, 2559, 229),
    (2303, 867, 2559, 889),
}

# VB-Cable configuration (already installed on host machine)
VB_CABLE_PLAYBACK_DEVICE = "CABLE Input"   # Matches "CABLE Input (VB-Audio Virtual Cable)"
VB_CABLE_RECORDING_DEVICE = "CABLE Output" # Matches "CABLE Output (VB-Audio Virtual Cable)"
VB_CABLE_TTS_ENABLED = True

BOT_SETTINGS = {
    "chat_mode": False,
    "silent_mode": False,
    "transcription_mode": True,
    "running": True,
}

MODERATION_ALLOWED_SENDERS: set[str] = set()
NATIVE_MODERATION_COMMANDS = {"unpunish", "unblockmic", "unban", "topic", "watchlist"}

TRIGGER_NAMES = (
    "kaekae", "!chat", "!chatoff", "!shutup", "!transcribe", "!transcribed",
    "!suppress", "!unsuppress", "!say", "!diss", "!who is", "!info on",
    "!grabs", "-", "!idk", "who kicked/blocked/banned/punished", "!happy",
    "!sad", "!mad", "!triggers",
)
