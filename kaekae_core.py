#!/usr/bin/env python3
"""
==============================================================================
KaeKae Core  (kaekae_core.py)  -  shared, cross-process-safe foundation
==============================================================================
One module every terminal imports so that:
  * all data paths are anchored to the project directory (never CWD dependent)
  * every JSON state file is written through an OS file lock + atomic replace,
    so Terminal 1 / Terminal 2 / Terminal 3 can never clobber each other
  * the one-hour "do not repeat a reply" gate is one shared implementation
  * every terminal writes structured telemetry to logs/<kind>_<date>.jsonl
  * terminals publish heartbeats so the HUD can report real liveness

Nothing here talks to Camfrog, the microphone, or the network.
==============================================================================
"""

import json
import os
import threading
import time
from datetime import datetime
from pathlib import Path
from typing import Any, Callable, Dict, Optional

# ------------------------------------------------------------------------------
# Paths - anchored to this file's folder, overridable with KAEKAE_HOME
# ------------------------------------------------------------------------------
ROOT = Path(os.environ.get("KAEKAE_HOME") or Path(__file__).resolve().parent)
LOGDIR = ROOT / "logs"
CONFIG_PATH = ROOT / "config.json"

STORE_OUTBOUND_GATE = "outbound_gate.json"
STORE_DEDUPE_CLAIMS = "dedupe_claims.json"
STORE_TALK_STATE = "talk_state.json"
STORE_HEARTBEATS = "terminal_heartbeats.json"
STORE_COMMAND_INBOX = "command_inbox.jsonl"

DEFAULT_CONFIG: Dict[str, Any] = {
    "cef_chat_scan_interval_seconds": 0.25,
    "engine": "qwen",
    "reply_engine": "",
    "qwen_model_id": "Qwen/Qwen3-TTS-12Hz-1.7B-CustomVoice",
    "qwen_speaker": "vivian",
    "edge_voice": "en-US-AvaNeural",
    "elevenlabs_api_key": "",
    "elevenlabs_persona": "valley",
    "voice": "en-US-AvaNeural",
    "voice_rate": "+12%",
    "voice_pitch": "+16Hz",
    "speak_timeout_s": 180,
    "brain_model": "qwen3-coder:latest",
    "brain_fallback": "llama3.2:latest",
    "brain_timeout_s": 8,
    "brain_keep_alive": "30m",
    "ollama_url": "http://127.0.0.1:11434",
    "bot_display_names": ["KaeKae_Toad", "KaeKaeBot-CamfrogAIAssistant", "KaeKae"],
    "talk_mode": "auto",
    "talk_stable_seconds": 1.0,
    "talk_grab_timeout_s": 6.0,
    "dup_reply_seconds": 3600,
    "screen_dup_seconds": 120,
    "known_sender_strict": True,
    "audio_input_device": "CABLE Output (VB-Audio Virtual Cable)",
    "audio_output_device": "CABLE Input (VB-Audio Virtual Cable)",
}


def p(name: str) -> Path:
    """Absolute path anchored to the project directory."""
    return ROOT / name


def _ensure_dir(path: Path) -> None:
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
    except Exception:
        pass


# ------------------------------------------------------------------------------
# Cross-process file lock (Windows msvcrt byte-range lock, portable fallback)
# ------------------------------------------------------------------------------
try:
    import msvcrt  # type: ignore
except ImportError:  # pragma: no cover - non Windows
    msvcrt = None

_THREAD_LOCKS: Dict[str, threading.RLock] = {}
_THREAD_LOCKS_GUARD = threading.Lock()


def _thread_lock_for(key: str) -> threading.RLock:
    with _THREAD_LOCKS_GUARD:
        lock = _THREAD_LOCKS.get(key)
        if lock is None:
            lock = threading.RLock()
            _THREAD_LOCKS[key] = lock
        return lock


class FileLock:
    """
    Exclusive advisory lock. Uses an OS byte-range lock so it is honoured
    ACROSS PROCESSES (Terminal 1 / 2 / 3), plus a thread lock for in-process
    safety. Always used as a context manager.
    """

    def __init__(self, target: Path, timeout: float = 8.0):
        self.lock_path = target.with_name(target.name + ".lock")
        self.timeout = timeout
        self._fd: Optional[int] = None
        self._thread_lock = _thread_lock_for(str(self.lock_path))

    def __enter__(self) -> "FileLock":
        self._thread_lock.acquire()
        _ensure_dir(self.lock_path)
        deadline = time.time() + self.timeout
        if msvcrt is None:
            return self  # thread lock only
        while True:
            try:
                fd = os.open(str(self.lock_path), os.O_RDWR | os.O_CREAT, 0o666)
            except Exception:
                if time.time() > deadline:
                    return self
                time.sleep(0.02)
                continue
            try:
                os.lseek(fd, 0, 0)
                msvcrt.locking(fd, msvcrt.LK_NBLCK, 1)
                self._fd = fd
                return self
            except OSError:
                os.close(fd)
                if time.time() > deadline:
                    return self
                time.sleep(0.02)

    def __exit__(self, exc_type, exc, tb) -> bool:
        if self._fd is not None:
            try:
                os.lseek(self._fd, 0, 0)
                msvcrt.locking(self._fd, msvcrt.LK_UNLCK, 1)
            except Exception:
                pass
            try:
                os.close(self._fd)
            except Exception:
                pass
            self._fd = None
        try:
            self._thread_lock.release()
        except Exception:
            pass
        return False


# ------------------------------------------------------------------------------
# Atomic, lock-protected JSON store
# ------------------------------------------------------------------------------
def read_json(name: str, default: Any = None) -> Any:
    path = p(name)
    fallback = default if default is not None else {}
    if not path.exists():
        return fallback
    try:
        with FileLock(path):
            raw = path.read_text(encoding="utf-8")
        return json.loads(raw) if raw.strip() else fallback
    except Exception:
        return fallback


def write_json_atomic(name: str, data: Any) -> bool:
    path = p(name)
    _ensure_dir(path)
    tmp = path.with_name(path.name + ".tmp")
    try:
        tmp.write_text(json.dumps(data, indent=2), encoding="utf-8")
        os.replace(str(tmp), str(path))  # atomic on NTFS
        return True
    except Exception:
        try:
            if tmp.exists():
                tmp.unlink()
        except Exception:
            pass
        return False


def locked_update(name: str, mutator: Callable[[Any], Any], default: Any = None) -> Any:
    """read -> mutator(data) -> atomic write, inside one cross-process lock."""
    path = p(name)
    with FileLock(path):
        data = read_json(name, default if default is not None else {})
        try:
            new_data = mutator(data)
        except Exception:
            return data
        if new_data is None:
            new_data = data
        write_json_atomic(name, new_data)
        return new_data


def append_jsonl(name: str, record: Dict[str, Any]) -> bool:
    path = p(name)
    _ensure_dir(path)
    line = json.dumps(record, default=str)
    with FileLock(path):
        try:
            with open(path, "a", encoding="utf-8") as f:
                f.write(line + "\n")
            return True
        except Exception:
            return False


# ------------------------------------------------------------------------------
# Config - one loader / one saver, shared by every terminal
# ------------------------------------------------------------------------------
_config_cache: Dict[str, Any] = {}
_config_mtime: float = 0.0


def load_config(force: bool = False) -> Dict[str, Any]:
    """Merged config (defaults + config.json). Auto-reloads when the file changes."""
    global _config_cache, _config_mtime
    try:
        mtime = CONFIG_PATH.stat().st_mtime if CONFIG_PATH.exists() else 0.0
    except Exception:
        mtime = 0.0
    if not force and _config_cache and mtime <= _config_mtime:
        return _config_cache
    data = dict(DEFAULT_CONFIG)
    try:
        if CONFIG_PATH.exists():
            with FileLock(CONFIG_PATH):
                raw = CONFIG_PATH.read_text(encoding="utf-8")
            if raw.strip():
                data.update(json.loads(raw))
    except Exception:
        pass
    _config_cache = data
    _config_mtime = mtime
    return data


def save_config(updates: Dict[str, Any], announce: bool = True) -> bool:
    """Merges updates into config.json under the cross-process lock."""
    global _config_cache, _config_mtime

    def _mutator(data: Any) -> Dict[str, Any]:
        merged = dict(DEFAULT_CONFIG)
        if isinstance(data, dict):
            merged.update(data)
        merged.update(updates)
        return merged

    result = locked_update(CONFIG_PATH.name, _mutator, {})
    _config_cache = {}
    _config_mtime = 0.0
    load_config(force=True)
    if announce:
        keys = ", ".join(f"{k}={v}" for k, v in updates.items())
        log_event("config", action="save", changed=keys)
        print(f"[CONFIG] Saved to {CONFIG_PATH.name}: {keys}")
    return bool(result)


# ------------------------------------------------------------------------------
# Telemetry - structured JSONL so behaviour can be analysed after a live run
# ------------------------------------------------------------------------------
def log_event(kind: str, **fields: Any) -> None:
    try:
        record = {"ts": datetime.now().isoformat(timespec="milliseconds"), "kind": kind}
        record.update(fields)
        LOGDIR.mkdir(exist_ok=True)
        append_jsonl(f"logs/{kind}_{datetime.now().strftime('%Y%m%d')}.jsonl", record)
    except Exception:
        pass


# ------------------------------------------------------------------------------
# One-hour outbound gate - "never reply with anything it said in the past hour"
# ------------------------------------------------------------------------------
def normalize_text(text: str) -> str:
    import re
    norm = re.sub(r"[^a-z0-9 ]+", " ", (text or "").lower())
    return " ".join(norm.split())


GATED_KINDS = {"reply", "spontaneous"}


def claim_or_suppress(kind: str, text: str, seconds: Optional[int] = None) -> bool:
    """
    Returns True when the outbound text may be sent, False when it repeats
    something already sent within the window (default dup_reply_seconds=3600).

    Only 'reply' and 'spontaneous' traffic is gated; system/command/ack messages
    always pass so state announcements ("Listening is ON.") are never suppressed.
    """
    if kind not in GATED_KINDS:
        return True
    norm = normalize_text(text)
    if not norm:
        return True
    cfg = load_config()
    window = int(seconds if seconds is not None else cfg.get("dup_reply_seconds", 3600))
    now = time.time()
    verdict = {"allowed": True}

    def _mutator(data: Any) -> Dict[str, Any]:
        store = data if isinstance(data, dict) else {}
        cutoff = now - window
        recent = {k: v for k, v in store.items() if isinstance(v, (int, float)) and v >= cutoff}
        if norm in recent:
            verdict["allowed"] = False
            verdict["previous_at"] = recent[norm]
        else:
            recent[norm] = now
        return recent

    locked_update(STORE_OUTBOUND_GATE, _mutator, {})
    if not verdict["allowed"]:
        log_event("gate", decision="suppress", kind=kind, text=text[:120],
                  age_s=round(now - verdict.get("previous_at", now), 1), window_s=window)
    else:
        log_event("gate", decision="allow", kind=kind, text=text[:120], window_s=window)
    return bool(verdict["allowed"])


def gate_snapshot(seconds: Optional[int] = None) -> Dict[str, float]:
    cfg = load_config()
    window = int(seconds if seconds is not None else cfg.get("dup_reply_seconds", 3600))
    cutoff = time.time() - window
    store = read_json(STORE_OUTBOUND_GATE, {})
    return {k: v for k, v in (store or {}).items() if isinstance(v, (int, float)) and v >= cutoff}


# ------------------------------------------------------------------------------
# Inbound claim store - one durable claim per captured chat message
# ------------------------------------------------------------------------------
def claim_message(signature: str, window: Optional[int] = None, room: str = "") -> bool:
    """
    Atomically claims a captured message. Returns True only for the FIRST caller,
    so a message that lingers on screen can never trigger the bot twice - even
    across restarts - because the claim is persisted before dispatch.

    `signature` must be built WITHOUT a timestamp (sender + normalised text).
    """
    sig = (signature or "").strip()
    if not sig:
        return False
    cfg = load_config()
    if window is None:
        window = int(cfg.get("screen_dup_seconds", 120))
    now = time.time()
    verdict = {"claim": False, "count": 0}

    def _mutator(data: Any) -> Dict[str, Any]:
        store = data if isinstance(data, dict) else {}
        cutoff = now - max(window, 3600)  # keep history an hour for auditability
        store = {k: v for k, v in store.items()
                 if isinstance(v, dict) and v.get("last_seen", 0) >= cutoff}
        entry = store.get(sig)
        if entry and (now - float(entry.get("last_seen", 0))) <= window:
            entry["count"] = int(entry.get("count", 1)) + 1
            entry["last_seen"] = now
            verdict["count"] = entry["count"]
            return store
        store[sig] = {"first_seen": now, "last_seen": now, "count": 1, "room": room}
        verdict["claim"] = True
        verdict["count"] = 1
        return store

    locked_update(STORE_DEDUPE_CLAIMS, _mutator, {})
    log_event("claim", signature=sig[:140], room=room, granted=verdict["claim"],
              seen_count=verdict["count"], window_s=window)
    return bool(verdict["claim"])


def make_chat_signature(room: str, sender: str, text: str) -> str:
    """Timestamp-free, jitter-immune identity for a captured chat message."""
    import re
    s = re.sub(r"[^a-z0-9_\-$]", "", (sender or "").lower())
    t = normalize_text(text)
    r = re.sub(r"[^a-z0-9]", "", (room or "").lower())[:40]
    return f"{r}|{s}|{t}"


# ------------------------------------------------------------------------------
# Terminal heartbeats - lets the HUD report real liveness instead of guessing
# ------------------------------------------------------------------------------
def heartbeat(terminal: str, **extra: Any) -> None:
    now = time.time()

    def _mutator(data: Any) -> Dict[str, Any]:
        store = data if isinstance(data, dict) else {}
        entry = store.get(terminal, {})
        entry.update({"last_seen": now, "pid": os.getpid()})
        if extra:
            entry.update(extra)
        store[terminal] = entry
        return store

    locked_update(STORE_HEARTBEATS, _mutator, {})


def read_heartbeats() -> Dict[str, Any]:
    return read_json(STORE_HEARTBEATS, {}) or {}


def terminal_alive(terminal: str, max_age: float = 15.0) -> bool:
    entry = read_heartbeats().get(terminal) or {}
    return (time.time() - float(entry.get("last_seen", 0))) <= max_age


# ------------------------------------------------------------------------------
# Cross-process talk ownership (belt to the Windows mutex braces)
# ------------------------------------------------------------------------------
def set_talk_state(holder: str, holding: bool, method: str = "none", **extra: Any) -> None:
    def _mutator(data: Any) -> Dict[str, Any]:
        state = data if isinstance(data, dict) else {}
        state.update({"holder": holder, "holding": bool(holding),
                      "method": method, "updated_at": time.time()})
        state.update(extra)
        return state
    locked_update(STORE_TALK_STATE, _mutator, {})


def get_talk_state() -> Dict[str, Any]:
    return read_json(STORE_TALK_STATE, {}) or {}


def dump_inbox_command(text: str, source: str = "t3") -> bool:
    """Silent command channel: Terminal 3 -> Terminal 1 (same claim path)."""
    return append_jsonl(STORE_COMMAND_INBOX, {
        "ts": datetime.now().isoformat(timespec="seconds"),
        "source": source,
        "text": text,
    })


def drain_inbox_commands() -> list:
    """Terminal 1 reads and clears the silent command inbox atomically."""
    path = p(STORE_COMMAND_INBOX)
    if not path.exists():
        return []
    drained: list = []
    with FileLock(path):
        try:
            raw = path.read_text(encoding="utf-8")
            if raw.strip():
                for line in raw.splitlines():
                    line = line.strip()
                    if not line:
                        continue
                    try:
                        drained.append(json.loads(line))
                    except Exception:
                        continue
            path.write_text("", encoding="utf-8")
        except Exception:
            pass
    return drained
