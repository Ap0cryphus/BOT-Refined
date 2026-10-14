"""Runtime configuration for the UI-Automation Camfrog bot with VB-Cable TTS & Live Mic Transcription."""

from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent
DATA_DIR = PROJECT_ROOT / "data"
LOG_DIR = PROJECT_ROOT / "logs"

DATABASE_PATH = DATA_DIR / "camfrog_bot.db"
SUPPRESSED_DATA_DIR = DATA_DIR / "suppressed_users"

# Calibrated Camfrog main window rectangle: [l=1273, t=0, r=2567, b=1399]
CALIBRATED_WINDOW_RECT = (1273, 0, 2567, 1399)

# Calibrated room tab click positions and bounds
ROOM_TAB_POSITIONS = {
    "Room List": (1390, 50, 1450, 80),
    "Players__Lounge": (1550, 50, 1650, 80),
}

ROOM_TAB_CLICK_POINTS = {
    "Room List": (1390, 50),
    "Players__Lounge": (1550, 50),
}

# Calibrated Camfrog UIA coordinates (screen coordinates in [left, top, right, bottom])
# 1. Chat Window Pane(50033) [l=1281,t=170,r=2355,b=1160] & Text(50020) [l=1332,t=189,r=2330,b=1160]
CHAT_WINDOW_RECT = (1281, 170, 2355, 1160)
CHAT_TEXT_RECT = (1332, 189, 2330, 1160)

# 2. Chat Txt Field Pane(50033) [l=1396,t=1206,r=2497,b=1241] (type message + press Enter)
CHAT_INPUT_RECT = (1396, 1206, 2497, 1241)

# 3. User List List(50008) [l=2359,t=141,r=2559,b=1160]
#    - Watch User List trending [l=2359,r=2559] up and down up to 100 users max
#    - Ignore "YOU ARE VIEWING #", "VIEWING #", and "LURKERS #" section headers
USER_LIST_RECT = (2359, 141, 2559, 1160)
MAX_ROOM_USERS = 100

# Ignored ListItem(50007) header rows and Top Gifters Pane(50033)
IGNORED_LISTITEM_RECTS = (
    (2359, 141, 2559, 163),  # ListItem(50007) 'YOU ARE VIEWING #' / header row
    (2303, 141, 2559, 163),  # Alternate ListItem(50007) header row
)
TOP_GIFTERS_RECT = (2359, 43, 2559, 86)  # Pane(50033) Top Gifters strip

# 4. Talk Button Button(50000) [l=1291,t=1169,r=1361,b=1195]
#    - Needs 2 clicks then hold to talk on microphone
TALK_BUTTON_RECT = (1291, 1169, 1361, 1195)
TALK_DOUBLE_CLICK_DELAY = 0.08

# 5. Active Microphone Speaker Button(50000) [l=1506,t=1174,r=1548,b=1190]
#    - Shows username of whoever is on mic (erases when no one is on mic)
#    - Bot waits until "KaeKae_Toad" appears here for >= 1.3 seconds before playing VB-Cable TTS
ACTIVE_SPEAKER_RECT = (1506, 1174, 1548, 1190)
BOT_USERNAME = "KaeKae_Toad"
MIC_CONFIRM_PERSIST_SECONDS = 1.3

# ==============================================================================
# PRECISION MICROPHONE GRAB SEQUENCE (per operator request)
#   The bot monitors the SPEAKER button until the name changes/disappears, then takes
#   3 EXTREMELY FAST clicks and HOLDS the 4th to transmit. While holding, it watches the
#   SPEAKER button for its own name "KaeKae_Toad" to persist:
#     * >= 1.3s  -> grab SUCCESSFUL, clip plays all the way through.
#     * < 3.0s total hold -> grab FAILED, RELEASE and REPEAT the whole attempt.
# ==============================================================================
MIC_GRAB_FAST_CLICKS = 3                 # 3 extremely fast clicks before the held 4th
MIC_GRAB_FAST_CLICK_DELAY = 0.03         # ~33ms between the fast clicks
MIC_GRAB_HOLD_MIN_SECONDS = 3.0          # bot's own name must persist >= 3.0s total to confirm a real hold
MIC_GRAB_CONFIRM_TIMEOUT_S = 5.0         # max time watching the SPEAKER button per attempt
MIC_GRAB_MAX_ATTEMPTS = 5                # repeat the grab cycle up to this many times before giving up
MIC_GRAB_RETRY_PAUSE_S = 0.20            # short pause between failed grab attempts

# VB-Cable virtual audio device settings + Realistic Microsoft Edge Neural TTS Voices
VB_CABLE_PLAYBACK_DEVICE = "CABLE Input"
VB_CABLE_RECORDING_DEVICE = "CABLE Output"
VB_CABLE_TTS_ENABLED = True

# Free, unlimited, realistic Microsoft Edge Neural TTS voices (switchable live via !voice <name>)
EDGE_TTS_DEFAULT_VOICE = "en-US-AriaNeural"
EDGE_TTS_VOICES = {
    "aria": "en-US-AriaNeural",
    "ava": "en-US-AvaMultilingualNeural",
    "andrew": "en-US-AndrewMultilingualNeural",
    "brian": "en-US-BrianMultilingualNeural",
    "jenny": "en-US-JennyNeural",
    "guy": "en-US-GuyNeural",
    "christopher": "en-US-ChristopherNeural",
    "steffan": "en-US-SteffanNeural",
    "sonia": "en-GB-SoniaNeural",
    "ryan": "en-GB-RyanNeural",
    "natasha": "en-AU-NatashaNeural",
}
EDGE_TTS_RATE = "+4%"
EDGE_TTS_PITCH = "+0Hz"

CAMFROG_PROCESS_NAMES = ("Camfrog.exe", "Camfrog", "CamfrogClient.exe")
CAMFROG_TITLE_HINTS = ("Players__Lounge", "Camfrog", "Lounge")
CAMFROG_WINDOW_TITLE_RE = r".*(?:Camfrog|Players__Lounge|Lounge).*"
IGNORED_USER_LIST_RECTS = IGNORED_LISTITEM_RECTS
USER_LIST_ITEM_X_SPAN = (2359, 2559)
UIA_CACHE_SECONDS = 0.025

# Ultra-fast polling interval (0.015s = ~66 polls/sec) so fast chat scrolling and quick mic grabs are never missed
POLL_INTERVAL_SECONDS = 0.015
CHAT_HISTORY_LIMIT = 500
MAX_CHAT_MESSAGE_LENGTH = 360

# ==============================================================================
# DEDICATED GPU ACCELERATION: AMD RADEON RX 9070 XT (DIRECTML / ROCm) & NVIDIA (CUDA)
# ==============================================================================
# Preferred hardware acceleration order requested: ROCm -> DirectML (AMD) -> CUDA (NVIDIA) -> CPU
USE_DEDICATED_GPU = True
PREFERRED_BACKEND_CHAIN = ["rocm", "directml", "cuda", "cpu"]
AMD_GPU_TARGET = "Radeon RX 9070 XT"
AMD_DIRECTML_DEVICE_INDEX = 0          # Main discrete AMD GPU on DirectX 12
CUDA_DEVICE_ORDER = "PCI_BUS_ID"
WHISPERX_MODEL_SIZE = "base.en"        # Fast English model for real-time Camfrog mic slices
WHISPERX_COMPUTE_TYPE_GPU = "float16"  # FP16 matrix compute on discrete GPU
WHISPERX_BATCH_SIZE = 16
PARALLEL_WORKER_THREADS = 8

BOT_SETTINGS = {
    "running": True,
    # Operator requirement: KaeKae_Toad must NEVER start in active chat mode. She boots in SILENT mode
    # (records everything to the DB + Terminal 3 transcription, but posts/announces nothing to the room)
    # and only starts mingling after an operator explicitly flips her on with `!chat`.
    "chat_mode": False,
    "silent_mode": True,
    "transcription_mode": True,
    "post_transcripts_to_chat": False,
    "tone": "neutral",
    "tts_voice": EDGE_TTS_DEFAULT_VOICE,
    "whisperx_enabled": True,
    "gpu_acceleration": True,
    "gpu_backend": "auto",             # Auto-resolves: ROCm -> DirectML (AMD) -> CUDA -> CPU
}

# Operators allowed to run native room moderation commands AND give KaeKae_Toad admin commands.
# Additional administrators can also be added dynamically via `!admin add <username>` in chat or `data/camfrog_calibration.json`.
MODERATION_ALLOWED_SENDERS: set[str] = {
    "KaeKae_Toad",
    "Stonerwayne1000",
    "Stonerwayne",
    "lockspeck",
    "OMGitsMyPHONE",
    "Rosie",
    "nico1ee",
}
NATIVE_MODERATION_COMMANDS = ("unpunish", "unblockmic", "unban", "topic", "watchlist", "kick", "ban", "punish", "blockmic")

# Runtime Calibration File (persists user's custom window/chat input/talk button bounds across restarts)
CALIBRATION_FILE_PATH = DATA_DIR / "camfrog_calibration.json"


def load_calibration_overrides() -> dict:
    """Load persisted calibration coordinates from data/camfrog_calibration.json if available."""
    import json
    if CALIBRATION_FILE_PATH.exists():
        try:
            data = json.loads(CALIBRATION_FILE_PATH.read_text(encoding="utf-8"))
            if isinstance(data, dict):
                extra_admins = data.get("allowed_admins")
                if isinstance(extra_admins, list):
                    for admin_name in extra_admins:
                        if isinstance(admin_name, str) and admin_name.strip():
                            MODERATION_ALLOWED_SENDERS.add(admin_name.strip())
                return data
        except Exception:
            pass
    return {}


def save_calibration_overrides(overrides: dict) -> None:
    """Persist calibrated window & chat input box coordinates to data/camfrog_calibration.json."""
    import json
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    existing = load_calibration_overrides()
    existing.update(overrides)
    CALIBRATION_FILE_PATH.write_text(json.dumps(existing, indent=2), encoding="utf-8")


# Load any persisted calibration overrides at import time
load_calibration_overrides()


# ==============================================================================
# LOCAL GPU TTS (Kokoro-82M ONNX on AMD DirectML) + portable XTTS-v2 model cache.
# Downloaded ONCE into data/models/ (offline after), never reinstalled per boot.
# ==============================================================================
LOCAL_KOKORO_MODEL_DIR = DATA_DIR / "models" / "kokoro"
LOCAL_KOKORO_ONNX_FILE = "kokoro-v1.0.onnx"
LOCAL_KOKORO_ONNX_FP16_FILE = "kokoro-v1.0-fp16.onnx"
LOCAL_KOKORO_VOICES_FILE = "voices-v1.0.bin"
LOCAL_KOKORO_READY_STAMP = LOCAL_KOKORO_MODEL_DIR / ".ready"
LOCAL_KOKORO_HF_REPO = "onnx-community/Kokoro-82M-v1.0-ONNX"
LOCAL_KOKORO_SAMPLE_RATE = 24000
# Women-only Kokoro presets for the SPECIAL MIC LINE (operator rule: no male voices).
# Default exception mirrors the Coqui Default slot: used purely to verify the pipeline.
KOKORO_DEFAULT_VOICE = "Kokoro Default (Test)"
KOKORO_FEMALE_VOICES: dict = {
    "Kokoro Heart": "af_heart",
    "Kokoro Bella": "af_bella",
    "Kokoro Sarah": "af_sarah",
    "Kokoro Emma": "bf_emma",
    "Kokoro Sky": "af_sky",
}
LOCAL_XTTS_MODEL_DIR = DATA_DIR / "models" / "xtts_v2"
LOCAL_XTTS_READY_STAMP = LOCAL_XTTS_MODEL_DIR / ".ready"
LOCAL_XTTS_HF_REPO = "coqui/XTTS-v2"
# Kokoro-82M ONNX files the `kokoro_onnx` package expects (a single combined model + voices bin).
# Hosted as public GitHub release assets (the onnx-community HF repo only ships per-voice bins +
# onnx/model.onnx, which do NOT match kokoro_onnx's loader). FP16 is preferred on DirectML/GPU;
# FP32 is the universal CPU fallback.
LOCAL_KOKORO_ONNX_URL = "https://github.com/thewh1teagle/kokoro-onnx/releases/download/model-files-v1.1/kokoro-v1.0.onnx"
LOCAL_KOKORO_ONNX_FP16_URL = "https://github.com/thewh1teagle/kokoro-onnx/releases/download/model-files-v1.1/kokoro-v1.0.fp16.onnx"
LOCAL_KOKORO_VOICES_URL = "https://github.com/thewh1teagle/kokoro-onnx/releases/download/model-files-v1.1/voices-v1.0.bin"

