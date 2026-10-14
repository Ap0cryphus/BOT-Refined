#!/usr/bin/env python3
"""
Portable environment bootstrapper for PepeFrog & Camfrog AI Bot.
Detects whatever folder the bot was unpacked into and whatever Python environment
(venv, Conda, or system Python) is running it, creates required runtime directories,
and automatically installs any missing packages before the bot starts.
"""

from __future__ import annotations

import argparse
import importlib
import importlib.util
import json
import os
import subprocess
import sys
import time
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent

# Optional-stack pip behavior: don't re-run heavy pip installs every launch.
OPTIONAL_STATE_FILE = BASE_DIR / "data" / ".optional_stack_state.json"
OPTIONAL_RETRY_WINDOW_S = 24 * 3600  # retry a previously failed optional install at most once per day
OPTIONAL_PIP_TIMEOUT_S = 600  # bound each optional pip attempt so a stalled resolver can't hang boot
REQUIRED_PIP_TIMEOUT_S = 600  # same protection for the required-packages pip call

# Core packages the bot needs to run. If any of these are missing the bot auto-installs them.
REQUIRED_MODULES: list[tuple[str, str, bool]] = [
    # (import_name, pip_spec, windows_only)
    ("numpy", "numpy>=1.24.0", False),
    ("PIL", "Pillow>=10.0.0", False),
    ("cv2", "opencv-python>=4.8.0", False),
    ("edge_tts", "edge-tts>=6.1.12", False),
    ("miniaudio", "miniaudio>=1.59", False),
    ("speech_recognition", "SpeechRecognition>=3.10.0", False),
    ("sounddevice", "sounddevice>=0.4.6", True),
    ("pywinauto", "pywinauto>=0.6.8", True),
    ("uiautomation", "uiautomation>=2.0.18", True),
    ("pyautogui", "PyAutoGUI>=0.9.54", True),
    ("keyboard", "keyboard>=0.13.5", True),
    ("comtypes", "comtypes>=1.2.0", True),
    ("win32gui", "pywin32>=306", True),
    # Fast GPU/CPU speech recognition engine (WhisperX pipeline primary; CTranslate2 backend).
    ("faster_whisper", "faster-whisper>=1.0.0", False),
    # AMD-first GPU acceleration: torch (CPU build here; DirectML/ROCm handled at runtime) + ONNX DirectML.
    ("torch", "torch>=2.1.0", False),
    ("onnxruntime", "onnxruntime>=1.17.0", False),
]

# Heavy GPU / voice-cloning packages that make the bot faster and richer but are NOT required to run.
# These are installed on a best-effort basis: the bot degrades gracefully to Edge Neural TTS + CPU
# Whisper if they are unavailable, so a failed/slow install NEVER blocks deployment anywhere.
OPTIONAL_MODULES: list[tuple[str, str, bool]] = [
    # (import_name, pip_spec, windows_only)
    # Coqui XTTS v2 voice cloning engine (Sample -> Clone -> Default) for KaeKae's real voice.
    ("TTS", "TTS>=0.22.0", False),
    # WhisperX word-level alignment (used when installed; faster-whisper is the fast primary).
    ("whisperx", "whisperx>=3.1.1", False),
    ("kokoro_onnx", "kokoro-onnx>=0.4.0", False),
    ("misaki", "misaki>=0.9.0", False),
    ("soundfile", "soundfile>=0.12.0", False),
    # AMD Radeon (RX 9070 XT) DirectML execution providers so torch/onnx run on the AMD GPU first.
    ("torch_directml", "torch-directml>=0.2.0", True),
    ("onnxruntime_directml", "onnxruntime-directml>=1.17.0", True),
]


def ensure_portable_directories() -> dict[str, Path]:
    """Create data/, data/suppressed/, data/voice_samples/, and logs/ relative to the unpacked script directory."""
    data_dir = BASE_DIR / "data"
    suppressed_dir = data_dir / "suppressed"
    voice_samples_dir = data_dir / "voice_samples"
    log_dir = BASE_DIR / "logs"
    voice_clone_dir = data_dir / "voice_clone"
    models_dir = data_dir / "models"
    for folder in (data_dir, suppressed_dir, voice_samples_dir, voice_clone_dir, models_dir, log_dir):
        folder.mkdir(parents=True, exist_ok=True)
    return {
        "base": BASE_DIR,
        "data": data_dir,
        "suppressed": suppressed_dir,
        "voice_samples": voice_samples_dir,
        "logs": log_dir,
    }


def detect_active_environment() -> str:
    """Return a human-readable description of the active Python environment."""
    venv = os.environ.get("VIRTUAL_ENV")
    conda = os.environ.get("CONDA_DEFAULT_ENV") or os.environ.get("CONDA_PREFIX")
    if venv:
        return f"virtualenv ({venv})"
    if conda:
        return f"conda ({conda})"
    return f"system Python ({sys.executable})"


def _dml_provider_present() -> bool:
    """True when onnxruntime exposes the DirectML execution provider (the onnxruntime-directml package)."""
    try:
        import onnxruntime as ort  # type: ignore[import-not-found]

        return "DmlExecutionProvider" in ort.get_available_providers()
    except Exception:
        return False


def _optional_present(mod_name: str) -> bool:
    """Fast presence probe that never executes heavy module code (no import_module hangs)."""
    if mod_name == "onnxruntime_directml":
        # The onnxruntime-directml wheel ships no `onnxruntime_directml` module: the provider
        # registers inside `onnxruntime` itself. Probing the import name would always "miss" and
        # reinstall every launch, so probe the provider listing instead.
        return _dml_provider_present()
    try:
        return importlib.util.find_spec(mod_name) is not None
    except Exception:
        return False


def find_missing_packages(*, check_windows_only: bool | None = None) -> list[str]:
    """Return pip package specs for any required modules not yet installed in sys.executable."""
    is_win = (os.name == "nt") if check_windows_only is None else bool(check_windows_only)
    missing: list[str] = []
    for mod_name, pip_spec, win_only in REQUIRED_MODULES:
        if win_only and not is_win:
            continue
        try:
            importlib.import_module(mod_name)
        except Exception:
            missing.append(pip_spec)
    return missing


def _load_optional_state() -> dict[str, dict[str, object]]:
    """Read the persisted optional-install stamp file (interpreter-keyed, best-effort)."""
    try:
        raw = OPTIONAL_STATE_FILE.read_text(encoding="utf-8")
        data = json.loads(raw)
        if isinstance(data, dict):
            return {str(k): v for k, v in data.items() if isinstance(v, dict)}
    except Exception:
        pass
    return {}


def _save_optional_state(state: dict[str, dict[str, object]]) -> None:
    """Persist the optional-install stamp file; a corrupt/unwritable cache never blocks boot."""
    try:
        OPTIONAL_STATE_FILE.parent.mkdir(parents=True, exist_ok=True)
        OPTIONAL_STATE_FILE.write_text(json.dumps(state, indent=2), encoding="utf-8")
    except Exception:
        pass


def _state_key(pip_spec: str) -> str:
    """Key stamp entries by interpreter + spec so a fresh venv/deploy re-validates correctly."""
    return f"{sys.executable}::{pip_spec}"


def install_optional_packages(
    *, quiet: bool = False, enabled: bool = True, force_retry: bool = False
) -> dict[str, bool]:
    """Best-effort install of heavy GPU / voice-cloning packages (Coqui XTTS, WhisperX, DirectML).

    These make the bot faster and give KaeKae her cloned voice, but they are NEVER required to run:
    the bot degrades gracefully to Edge Neural TTS + CPU Whisper if they are unavailable. A slow or
    failed install therefore never blocks deployment anywhere — each package is attempted in isolation.

    Launch-cost rules (so installed packages are never reinstalled and a stall never hangs boot):
      * already importable  -> marked ready, zero pip calls;
      * failed within OPTIONAL_RETRY_WINDOW_S (flat 24h) -> skipped this launch (fast boot);
      * otherwise one bounded pip attempt (OPTIONAL_PIP_TIMEOUT_S) and the outcome is stamped.
    """
    results: dict[str, bool] = {}
    if not enabled:
        return results
    is_win = os.name == "nt"
    state = _load_optional_state()
    now = time.time()
    state_changed = False
    for mod_name, pip_spec, win_only in OPTIONAL_MODULES:
        if win_only and not is_win:
            continue
        # Fast path: present -> ready, NEVER reinstall.
        if _optional_present(mod_name):
            results[mod_name] = True
            key = _state_key(pip_spec)
            if state.get(key, {}).get("ok") is not True:
                state[key] = {"ok": True, "attempted_at": now}
                state_changed = True
            continue
        # Cached miss within the retry window -> skip pip this launch (fast boot).
        key = _state_key(pip_spec)
        entry = state.get(key, {})
        attempted_at = float(entry.get("attempted_at", 0.0) or 0.0)
        if not force_retry and entry.get("ok") is False and (now - attempted_at) < OPTIONAL_RETRY_WINDOW_S:
            if not quiet:
                print(f"[setup_env] Skipping optional {pip_spec} (cached miss; retry with --retry-optional) ...")
            results[mod_name] = False
            continue
        if not quiet:
            print(f"[setup_env] Installing optional GPU/voice package (best-effort): {pip_spec} ...")
        cmd = [
            sys.executable,
            "-m",
            "pip",
            "install",
            "--disable-pip-version-check",
            "--quiet",
            "--prefer-binary",
            pip_spec,
        ]
        creationflags = 0x08000000 if os.name == "nt" else 0  # CREATE_NO_WINDOW on Windows
        try:
            # Bounded attempt: a stalled resolver (e.g. huge TTS tree) can never hang boot.
            proc = subprocess.run(cmd, check=False, creationflags=creationflags, timeout=OPTIONAL_PIP_TIMEOUT_S)
            results[mod_name] = proc.returncode == 0
        except Exception:
            results[mod_name] = False
        state[key] = {"ok": bool(results[mod_name]), "attempted_at": time.time()}
        state_changed = True
    if state_changed:
        _save_optional_state(state)
    return results


def ensure_local_tts_assets(*, quiet: bool = False) -> dict:
    """Download Kokoro ONNX (~310MB) + XTTS-v2 (~2GB) ONCE into data/models/ (offline after).

    Writes .ready stamps so later boots skip the download. Never raises; returns status dict.
    Honors HF_HUB_OFFLINE=1 (skip network when already stamped).
    """
    from config import (LOCAL_KOKORO_MODEL_DIR, LOCAL_KOKORO_ONNX_FILE,
                        LOCAL_KOKORO_ONNX_FP16_FILE, LOCAL_KOKORO_VOICES_FILE,
                        LOCAL_KOKORO_READY_STAMP, LOCAL_KOKORO_ONNX_URL,
                        LOCAL_KOKORO_ONNX_FP16_URL, LOCAL_KOKORO_VOICES_URL,
                        LOCAL_XTTS_MODEL_DIR, LOCAL_XTTS_READY_STAMP, LOCAL_XTTS_HF_REPO)
    out = {"kokoro": False, "xtts": False}
    try:
        LOCAL_KOKORO_MODEL_DIR.mkdir(parents=True, exist_ok=True)
    except Exception:
        pass
    try:
        LOCAL_XTTS_MODEL_DIR.mkdir(parents=True, exist_ok=True)
    except Exception:
        pass
    offline = str(os.environ.get("HF_HUB_OFFLINE", "")).strip() == "1"

    def _http_download(url: str, dest: Path) -> bool:
        """Stream a file from a public URL to `dest` (atomic temp -> rename). Returns True on success."""
        import urllib.request

        tmp = dest.with_suffix(dest.suffix + ".part")
        try:
            req = urllib.request.Request(url, headers={"User-Agent": "BOT-Refined-setup/1.0"})
            with urllib.request.urlopen(req, timeout=600) as resp, open(tmp, "wb") as fh:
                while True:
                    chunk = resp.read(1024 * 1024)
                    if not chunk:
                        break
                    fh.write(chunk)
            tmp.replace(dest)
            return dest.exists() and dest.stat().st_size > 1024
        except Exception:
            try:
                if tmp.exists():
                    tmp.unlink()
            except Exception:
                pass
            raise

    # Kokoro: onnx (fp32 + fp16) + combined voices bin, from public GitHub release assets.
    try:
        onnx_p = LOCAL_KOKORO_MODEL_DIR / LOCAL_KOKORO_ONNX_FILE
        fp16_p = LOCAL_KOKORO_MODEL_DIR / LOCAL_KOKORO_ONNX_FP16_FILE
        voices_p = LOCAL_KOKORO_MODEL_DIR / LOCAL_KOKORO_VOICES_FILE
        if LOCAL_KOKORO_READY_STAMP.exists() and onnx_p.exists() and voices_p.exists():
            out["kokoro"] = True
        elif not offline:
            try:
                # FP32 model (universal CPU fallback) + combined voices bin are REQUIRED.
                if not onnx_p.exists() or onnx_p.stat().st_size < 1024:
                    if not quiet:
                        print("[setup_env] Downloading Kokoro fp32 ONNX (~310MB)...")
                    _http_download(LOCAL_KOKORO_ONNX_URL, onnx_p)
                if not voices_p.exists() or voices_p.stat().st_size < 1024:
                    if not quiet:
                        print("[setup_env] Downloading Kokoro voices bin (~28MB)...")
                    _http_download(LOCAL_KOKORO_VOICES_URL, voices_p)
                # FP16 model (preferred on DirectML/GPU) is BEST-EFFORT — fp32 remains the fallback.
                if not fp16_p.exists() or fp16_p.stat().st_size < 1024:
                    try:
                        if not quiet:
                            print("[setup_env] Downloading Kokoro fp16 ONNX (~163MB, GPU-preferred)...")
                        _http_download(LOCAL_KOKORO_ONNX_FP16_URL, fp16_p)
                    except Exception as fp16_exc:
                        if not quiet:
                            print(f"[setup_env] Kokoro fp16 download deferred ({fp16_exc}); fp32 still usable.")
                if onnx_p.exists() and voices_p.exists():
                    LOCAL_KOKORO_READY_STAMP.write_text("ready", encoding="utf-8")
                    out["kokoro"] = True
                    if not quiet:
                        print("[setup_env] Kokoro local TTS assets ready.")
            except Exception as exc:
                if not quiet:
                    print(f"[setup_env] Kokoro asset download deferred ({exc}).")
        if offline and not out["kokoro"] and not quiet:
            print("[setup_env] HF_HUB_OFFLINE=1 and Kokoro assets missing; Edge TTS remains active.")
    except Exception:
        pass
    # XTTS: snapshot once
    try:
        if LOCAL_XTTS_READY_STAMP.exists():
            out["xtts"] = True
        elif not offline:
            try:
                from huggingface_hub import snapshot_download  # type: ignore
                snapshot_download(repo_id=LOCAL_XTTS_HF_REPO, local_dir=str(LOCAL_XTTS_MODEL_DIR),
                                  local_dir_use_symlinks=False)
                LOCAL_XTTS_READY_STAMP.write_text("ready", encoding="utf-8")
                out["xtts"] = True
                if not quiet:
                    print("[setup_env] XTTS-v2 local model cache ready.")
            except Exception as exc:
                if not quiet:
                    print(f"[setup_env] XTTS asset download deferred ({exc}).")
    except Exception:
        pass
    return out


def bootstrap_environment(

    *,
    quiet: bool = False,
    install_missing: bool = True,
    auto_install: bool | None = None,
    install_optional: bool = True,
    retry_optional: bool = False,
) -> bool:
    """Ensure portable directories exist and auto-install missing dependencies into sys.executable.

    Required packages are installed first; then the optional GPU / voice-cloning stack is installed
    on a best-effort basis (each in isolation) so a heavy or failing install never blocks the bot.
    """
    dirs = ensure_portable_directories()
    try:
        (dirs['data'] / 'models' / 'kokoro').mkdir(parents=True, exist_ok=True)
        (dirs['data'] / 'models' / 'xtts_v2').mkdir(parents=True, exist_ok=True)
        (dirs['data'] / 'voice_clone').mkdir(parents=True, exist_ok=True)
    except Exception:
        pass
    try:
        ensure_local_tts_assets(quiet=quiet)
    except Exception:
        pass
    if auto_install is not None:
        install_missing = bool(auto_install)
    missing = find_missing_packages()
    if not missing:
        if not quiet:
            print(f"[setup_env] Portable root: {BASE_DIR}")
            print(f"[setup_env] Active environment: {detect_active_environment()} — all dependencies ready.")
    elif not install_missing:
        if not quiet:
            print(f"[setup_env] Missing packages in {detect_active_environment()}: {', '.join(missing)}")
        return False
    else:
        if not quiet:
            print(f"[setup_env] Installing missing packages into {detect_active_environment()}: {', '.join(missing)}")
        cmd = [
            sys.executable,
            "-m",
            "pip",
            "install",
            "--disable-pip-version-check",
            "--quiet",
            *missing,
        ]
        creationflags = 0x08000000 if os.name == "nt" else 0  # CREATE_NO_WINDOW on Windows
        try:
            proc = subprocess.run(cmd, check=False, creationflags=creationflags, timeout=REQUIRED_PIP_TIMEOUT_S)
        except Exception:
            return False
        if proc.returncode != 0:
            return False

    # Best-effort install of the optional GPU / voice-cloning stack (never blocks the bot).
    if install_missing and install_optional:
        opt_results = install_optional_packages(quiet=quiet, force_retry=retry_optional)
        if not quiet:
            ready = [m for m, ok in opt_results.items() if ok]
            if ready:
                print(f"[setup_env] Optional GPU/voice stack ready: {', '.join(ready)}")
            else:
                print("[setup_env] Optional GPU/voice stack not installed — bot will run on Edge TTS + CPU Whisper.")
    return True


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Portable directory & dependency bootstrapper")
    parser.add_argument("--test", action="store_true", help="Verify portable directories without running pip install")
    parser.add_argument("--quiet", action="store_true", help="Suppress normal status output")
    parser.add_argument("--no-optional", action="store_true", help="Skip the optional GPU/voice stack entirely")
    parser.add_argument(
        "--retry-optional",
        action="store_true",
        help="Ignore the cached-miss stamp and force one fresh optional-install attempt",
    )
    args = parser.parse_args(argv)

    dirs = ensure_portable_directories()
    if args.test:
        print(f"Portable root verified: {dirs['base']}")
        print(f"Active Python environment: {detect_active_environment()}")
        return 0

    ok = bootstrap_environment(
        quiet=args.quiet,
        install_missing=True,
        install_optional=not args.no_optional,
        retry_optional=args.retry_optional,
    )
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
