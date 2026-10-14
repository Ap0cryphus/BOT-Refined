#!/usr/bin/env python3
"""
main.py — Unified KaeKae_Toad & PepeFrog Desktop GUI + Precision Automation Orchestrator
========================================================================================

Unites the full KaeKae_Toad Camfrog Bot (`camfrog_bot.py` + `ui_automation.py`) with the
PepeFrog Cross-Game & Heist Optimization Engine (`uia_interface.py`, `vision_analyzer.py`, `strategy_core.py`):

1. AUTOMATIC SILENT LISTENING ON LAUNCH (AUTO-SPIN OFF BY DEFAULT):
   - When the GUI opens, KaeKae_Toad's room listener starts automatically in the background with NO chat announcement!
   - She immediately watches the room, records all user messages/attributes/genders/biographies into the enhanced SQLite DB,
     tracks `SPEAKER_ON_MIC`, and responds to all 20 KaeKae_Toad triggers (`kaekae`, `!chat`, `!chatoff`, `!shutup`,
     `!transcribe`, `!transcribed`, `!suppress`, `!unsuppress`, `!say`, `!diss`, `!who is`, `!info on`, `!grabs`, `-`,
     `!idk`, `who kicked/blocked/banned/punished`, `!happy`, `!sad`, `!mad`, `!triggers`).
   - Auto-Spin starts OFF (`auto_spin_enabled = False`) and includes a dedicated `🛑 AUTO-SPIN: OFF` button to stop
     auto-spinning at any moment while keeping KaeKae_Toad running normally.

2. FULL-WINDOW STRETCHED GUI ARTWORK + TRANSLUCENT OPACITY SPLIT TERMINALS:
   - Stretches the Feminine Ultra Instinct KaeKae Warrior + Crowned Gambling Frog artwork (`LOGO FOR GUI.png`) across the
     entire program GUI background, with dark translucent opacity over the 2 Split Terminals so all text is crisp and readable:
     * TERMINAL 1 (Left): Incoming Room Information (Chat, Presence, `SPEAKER_ON_MIC`, Live Mic Transcriptions, User DB events)
     * TERMINAL 2 (Right): Outgoing Bot Actions & All-Spins Analyzer (Every `!spin` in the room, PAT Win/Loss/Jackpot EV,
       Timing Window Optimization, Bot Replies, and Strategy Telemetry)
"""

from __future__ import annotations

import argparse
import ctypes
import json
import os
import random
import subprocess
import sys
import threading
import time
from datetime import datetime
from pathlib import Path
from typing import Any, Callable

sys.path.insert(0, str(Path(__file__).resolve().parent))

from camfrog_bot import CamfrogBot
from config import (
    ACTIVE_SPEAKER_RECT,
    BOT_USERNAME,
    CHAT_INPUT_RECT,
    CHAT_WINDOW_RECT,
    EDGE_TTS_DEFAULT_VOICE,
    EDGE_TTS_VOICES,
    MIC_CONFIRM_PERSIST_SECONDS,
    TALK_BUTTON_RECT,
    USER_LIST_RECT,
)
from strategy_core import (
    LOTTO_TICKET_COST_PAT,
    RANDOM_SPIN_MAX_SECONDS,
    RANDOM_SPIN_MIN_SECONDS,
    SPIN_COOLDOWN_SECONDS,
    SPIN_FLAT_COST_PAT,
    PepeFrogStrategyEngine,
)
from uia_interface import UIAInterface
from ui_automation import (
    COQUI_CLONE_VOICE,
    COQUI_DEFAULT_VOICE,
    KOKORO_DEFAULT_VOICE,
    coqui_voice_catalog,
    edge_female_voice_catalog,
    kokoro_voice_catalog,
)
from vision_analyzer import SpinVisualObservation, VisionAnalyzer

try:
    import keyboard  # type: ignore[import-not-found]
except ImportError:
    keyboard = None  # type: ignore[assignment]

try:
    import tkinter as tk
    from tkinter import font as tkfont
    from tkinter import ttk
    TK_GUI_AVAILABLE = True
except Exception:
    tk = None  # type: ignore[assignment]
    tkfont = None  # type: ignore[assignment]
    ttk = None  # type: ignore[assignment]
    TK_GUI_AVAILABLE = False

PRECISION_SPIN_INTERVAL_S: float = 20.200
FAILSAFE_HOLD_THRESHOLD_S: float = 0.300  # 300ms hold on 'Esc' or 'q'


def precision_sleep_until(
    target_perf_counter: float,
    abort_event: threading.Event,
    spin_stop_event: threading.Event | None = None,
) -> bool:
    """High-precision sleep array using `time.perf_counter()` that wakes immediately if abort_event or spin_stop_event is set."""
    while not abort_event.is_set():
        if spin_stop_event is not None and spin_stop_event.is_set():
            return False
        remaining = target_perf_counter - time.perf_counter()
        if remaining <= 0.0:
            return True
        if remaining > 0.015:
            time.sleep(min(0.005, remaining * 0.5))
        else:
            while time.perf_counter() < target_perf_counter:
                if abort_event.is_set() or (spin_stop_event is not None and spin_stop_event.is_set()):
                    return False
            return True
    return False


if TK_GUI_AVAILABLE:

    class RoundedButton(tk.Canvas):  # type: ignore[misc]
        """A rounded-corner button drawn on a Canvas (tk.Button-compatible `config` API).

        Gives the whole GUI a clean, modern look: flat rounded pill with hover/press
        feedback. Supports `text`, `bg`, `fg`, `activebackground`, `activeforeground`,
        `font`, `padx`, `pady`, `command`, `state`, and accepts (and ignores) the extra
        tk.Button-style keywords used across this codebase (`relief`, `bd`,
        `highlightthickness`, `highlightbackground`, `cursor`).
        """

        _IGNORED_KW = ("relief", "bd", "highlightthickness", "highlightbackground", "cursor", "takefocus")

        def __init__(self, master: Any, **kwargs: Any) -> None:
            self._ready = False
            self._text = str(kwargs.pop("text", ""))
            self._bg = str(kwargs.pop("bg", "#1E293B"))
            self._fg = str(kwargs.pop("fg", "#F8FAFC"))
            self._active_bg = str(kwargs.pop("activebackground", self._shade(self._bg, 1.18)))
            self._active_fg = str(kwargs.pop("activeforeground", self._fg))
            self._font = kwargs.pop("font", ("Segoe UI", 9, "bold"))
            self._padx = int(kwargs.pop("padx", 10))
            self._pady = int(kwargs.pop("pady", 3))
            self._command = kwargs.pop("command", None)
            self._state = str(kwargs.pop("state", "normal"))
            for key in self._IGNORED_KW:
                kwargs.pop(key, None)
            cursor = kwargs.pop("cursor", "hand2")
            kwargs.pop("width", None)
            kwargs.pop("height", None)

            font_obj = tkfont.Font(font=self._font)
            width = max(24, font_obj.measure(self._text) + 2 * self._padx)
            height = max(20, font_obj.metrics("linespace") + 2 * self._pady)
            super().__init__(
                master,
                width=width,
                height=height,
                bg=master.cget("bg"),
                highlightthickness=0,
                bd=0,
                cursor=cursor,
            )
            self._hover = False
            self._pressed = False
            self._radius = max(6, height // 2)
            self.bind("<Enter>", self._on_enter)
            self.bind("<Leave>", self._on_leave)
            self.bind("<ButtonPress-1>", self._on_press)
            self.bind("<ButtonRelease-1>", self._on_release)
            self._ready = True
            self.redraw()

        # ------------------------------------------------------------- helpers
        @staticmethod
        def _shade(hex_color: str, factor: float) -> str:
            try:
                c = hex_color.lstrip("#")
                r, g, b = (int(c[i:i + 2], 16) for i in (0, 2, 4))
                clamp = lambda v: max(0, min(255, int(v * factor)))  # noqa: E731
                return f"#{clamp(r):02X}{clamp(g):02X}{clamp(b):02X}"
            except Exception:
                return hex_color

        def _current_colors(self) -> tuple[str, str]:
            if self._state == "disabled":
                return "#334155", "#94A3B8"
            if self._pressed:
                return self._shade(self._bg, 0.82), self._fg
            if self._hover:
                return self._active_bg, self._active_fg
            return self._bg, self._fg

        def redraw(self) -> None:
            if not getattr(self, "_ready", False):
                return
            self.delete("all")
            w = int(self.cget("width"))
            h = int(self.cget("height"))
            fill, text_color = self._current_colors()
            r = min(self._radius, h // 2, w // 2)
            # Rounded rectangle: 4 corner arcs (pieslice) + 4 edge rectangles.
            self.create_arc(0, 0, 2 * r, 2 * r, start=90, extent=90, fill=fill, outline=fill, style="pieslice")
            self.create_arc(w - 2 * r, 0, w, 2 * r, start=0, extent=90, fill=fill, outline=fill, style="pieslice")
            self.create_arc(w - 2 * r, h - 2 * r, w, h, start=270, extent=90, fill=fill, outline=fill, style="pieslice")
            self.create_arc(0, h - 2 * r, 2 * r, h, start=180, extent=90, fill=fill, outline=fill, style="pieslice")
            self.create_rectangle(r, 0, w - r, h, fill=fill, outline=fill)
            self.create_rectangle(0, r, w, h - r, fill=fill, outline=fill)
            self.create_text(w // 2, h // 2, text=self._text, fill=text_color, font=self._font)

        # ------------------------------------------------------------- events
        def _on_enter(self, _event: Any) -> None:
            if self._state != "disabled":
                self._hover = True
                self.redraw()

        def _on_leave(self, _event: Any) -> None:
            self._hover = False
            self._pressed = False
            self.redraw()

        def _on_press(self, _event: Any) -> None:
            if self._state != "disabled":
                self._pressed = True
                self.redraw()

        def _on_release(self, _event: Any) -> None:
            was_pressed = self._pressed
            self._pressed = False
            self.redraw()
            if was_pressed and self._state != "disabled" and callable(self._command):
                self._command()

        # ----------------------------------------------------- tk.Button API
        def _apply_option(self, key: str, value: Any) -> bool:
            if key == "text":
                self._text = str(value)
            elif key == "bg":
                self._bg = str(value)
            elif key == "fg":
                self._fg = str(value)
            elif key == "activebackground":
                self._active_bg = str(value)
            elif key == "activeforeground":
                self._active_fg = str(value)
            elif key == "font":
                self._font = value
            elif key == "command":
                self._command = value
            elif key == "state":
                self._state = str(value)
            else:
                return False
            return True

        def config(self, cnf: Any = None, **kw: Any) -> None:
            self.configure(cnf, **kw)

        def configure(self, cnf: Any = None, **kw: Any) -> None:
            merged: dict[str, Any] = {}
            if isinstance(cnf, dict):
                merged.update(cnf)
            merged.update(kw)
            changed = False
            for key, value in list(merged.items()):
                if self._apply_option(key, value):
                    changed = True
                elif key not in self._IGNORED_KW:
                    try:
                        super().configure(**{key: value})
                    except Exception:
                        pass
            if changed:
                self.redraw()

    def make_rounded_btn(parent: Any, **kwargs: Any) -> "RoundedButton":
        """Factory: build a rounded-corner button with sensible modern defaults."""
        kwargs.setdefault("relief", "flat")
        kwargs.setdefault("bd", 0)
        kwargs.setdefault("highlightthickness", 1)
        kwargs.setdefault("cursor", "hand2")
        return RoundedButton(parent, **kwargs)

else:  # pragma: no cover - tkinter unavailable (headless)

    def make_rounded_btn(parent: Any, **kwargs: Any) -> Any:  # type: ignore[misc]
        raise RuntimeError("Tkinter is unavailable in this environment.")


class GlobalFailSafeMonitor:
    """Monitors 'Esc' or 'q' hold for >= 300ms via `keyboard` library (or Win32 GetAsyncKeyState) to abort cleanly."""

    VK_ESCAPE = 0x1B
    VK_Q = 0x51

    def __init__(
        self,
        abort_event: threading.Event,
        on_abort: Callable[[str], None] | None = None,
        hold_seconds: float = FAILSAFE_HOLD_THRESHOLD_S,
    ) -> None:
        self.abort_event = abort_event
        self.on_abort = on_abort
        self.hold_seconds = hold_seconds
        self._thread: threading.Thread | None = None
        self._hold_started_at: float | None = None

    def _is_esc_or_q_pressed(self) -> tuple[bool, str]:
        if keyboard is not None:
            try:
                if keyboard.is_pressed("esc"):
                    return True, "ESC"
                if keyboard.is_pressed("q"):
                    return True, "Q"
            except Exception:
                pass
        if os.name == "nt":
            try:
                user32 = ctypes.windll.user32
                if user32.GetAsyncKeyState(self.VK_ESCAPE) & 0x8000:
                    return True, "ESC"
                if user32.GetAsyncKeyState(self.VK_Q) & 0x8000:
                    return True, "Q"
            except Exception:
                pass
        return False, ""

    def start(self) -> None:
        if self._thread is not None and self._thread.is_alive():
            return
        self._thread = threading.Thread(target=self._watch_loop, name="FailSafeHotkeyWatcher", daemon=True)
        self._thread.start()

    def _watch_loop(self) -> None:
        while not self.abort_event.is_set():
            pressed, key_name = self._is_esc_or_q_pressed()
            now = time.perf_counter()
            if pressed:
                if self._hold_started_at is None:
                    self._hold_started_at = now
                elif (now - self._hold_started_at) >= self.hold_seconds:
                    self.abort_event.set()
                    if keyboard is not None:
                        try:
                            keyboard.unhook_all()
                        except Exception:
                            pass
                    if self.on_abort is not None:
                        self.on_abort(
                            f"[FAIL-SAFE] '{key_name}' held >= {int(self.hold_seconds * 1000)}ms! "
                            "Stripped event loops and aborted all background threads cleanly."
                        )
                    return
            else:
                self._hold_started_at = None
            time.sleep(0.015)


class PepeFrogOrchestrator:
    """Unified execution orchestrator running BOTH KaeKae_Toad (`CamfrogBot`) and the PepeFrog Spin/Heist Optimizer."""

    def __init__(
        self,
        *,
        dry_run: bool = False,
        initial_wallet_pat: int = 25_000,
        initial_jackpot_pat: int = 2_850_000,
        spin_interval_s: float = PRECISION_SPIN_INTERVAL_S,
        random_spin_mode: bool = False,
        auto_spin_enabled: bool = False,
        random_min_s: float = RANDOM_SPIN_MIN_SECONDS,
        random_max_s: float = RANDOM_SPIN_MAX_SECONDS,
        log_callback: Callable[[str], None] | None = None,
    ) -> None:
        self.dry_run = dry_run
        self.spin_interval_s = max(0.05, float(spin_interval_s))
        # Auto-Spin is OFF on app launch until the user explicitly presses Auto-Spin or checks 1-3m Random!
        self.auto_spin_enabled: bool = bool(auto_spin_enabled)
        self.random_spin_mode: bool = bool(random_spin_mode)
        self.random_min_s = float(random_min_s)
        self.random_max_s = float(random_max_s)
        self.abort_event = threading.Event()
        self.spin_stop_event = threading.Event()
        if not self.auto_spin_enabled:
            self.spin_stop_event.set()

        self._log_listeners: list[Callable[[str], None]] = []
        if log_callback is not None:
            self._log_listeners.append(log_callback)

        # 1. Initialize KaeKae_Toad (CamfrogBot) first and share its exact CamfrogUIAutomation adapter + log stream
        self.kaekae_bot = CamfrogBot(dry_run=dry_run, log_callback=self.emit_log)
        # Stream Coqui/XTTS voice-clone & synthesis progress straight into the operator terminals (Terminal 3).
        self.kaekae_bot.ui_automation.log_callback = self.emit_log
        self.uia = UIAInterface(
            dry_run=dry_run,
            log_callback=self.emit_log,
            shared_adapter=self.kaekae_bot.ui_automation,
        )
        self.vision = VisionAnalyzer(
            ocr_provider=self.uia.adapter._ocr_screen_rect if not dry_run else None,
        )
        self.vision.observed_jackpot_pool = initial_jackpot_pat
        self.strategy = PepeFrogStrategyEngine(
            initial_wallet_pat=initial_wallet_pat,
            initial_jackpot_pat=initial_jackpot_pat,
        )
        self.failsafe = GlobalFailSafeMonitor(self.abort_event, on_abort=self._on_failsafe_triggered)
        self._worker_thread: threading.Thread | None = None
        self._kaekae_thread: threading.Thread | None = None
        self.next_spin_countdown_s: float = 0.0
        self.announce_winnings_in_chat: bool = False
        self.auto_heist_enabled: bool = True
        self._awaiting_spin_result_until: float = 0.0
        self._last_recorded_obs_ts: float = 0.0
        self._last_room_spin_mono: float = 0.0
        self._last_room_spin_user: str = ""

    def _on_failsafe_triggered(self, msg: str) -> None:
        self.auto_spin_enabled = False
        self.spin_stop_event.set()
        self.next_spin_countdown_s = 0.0
        self.kaekae_bot.kill_switch()
        self.emit_log(msg)

    def add_log_listener(self, callback: Callable[[str], None]) -> None:
        self._log_listeners.append(callback)

    def emit_log(self, line: str) -> None:
        ts = datetime.now().strftime("%H:%M:%S.%f")[:-3]
        formatted = f"[{ts}] {line}"
        # Console-safe print: legacy cp1252/GBK consoles cannot encode emoji/status glyphs,
        # so fall back to a replace pass instead of crashing the bot mid-loop.
        try:
            print(formatted, flush=True)
        except UnicodeEncodeError:
            enc = getattr(sys.stdout, "encoding", None) or "utf-8"
            print(formatted.encode(enc, errors="replace").decode(enc), flush=True)
        for listener in list(self._log_listeners):
            try:
                listener(formatted)
            except Exception:
                pass

    def run_async(self, fn: Callable[[], Any], name: str = "AsyncGUIAction") -> None:
        """Run any UIA / calibration / chat / heist action on a non-blocking daemon thread so the GUI never lags."""
        def _wrapped() -> None:
            try:
                fn()
            except Exception as exc:
                self.emit_log(f"[{name} ERR] {exc}")

        threading.Thread(target=_wrapped, name=name, daemon=True).start()

    def set_auto_spin_state(self, enabled: bool, *, random_1_to_3_min: bool | None = None) -> None:
        """Explicitly start or immediately stop the Auto-Spin loop (without stopping KaeKae_Toad's room listener)."""
        if random_1_to_3_min is not None:
            self.random_spin_mode = bool(random_1_to_3_min)
        self.auto_spin_enabled = bool(enabled)
        if self.auto_spin_enabled:
            self.abort_event.clear()
            self.spin_stop_event.clear()
            mode_lbl = (
                f"1–3 Min Randomized ({self.random_min_s:.0f}s–{self.random_max_s:.0f}s)"
                if self.random_spin_mode
                else f"Fixed {self.spin_interval_s:.2f}s Cooldown"
            )
            self.emit_log(f"[AUTO-SPIN ARMED 🎰] Auto-Spin turned ON ({mode_lbl}). Dispatching !spin cycle...")
            self.start_background_loop(start_spinner=True)
        else:
            self.spin_stop_event.set()
            self.next_spin_countdown_s = 0.0
            self.emit_log(
                "[AUTO-SPIN: OFF 🛑] Auto-Spin stopped immediately. KaeKae_Toad room listener & triggers remain active!"
            )

    def start_silent_listening(self) -> None:
        """Automatically start KaeKae_Toad's room listener on launch with ZERO chat announcement and Auto-Spin OFF.

        Operator requirement: she ALWAYS boots in silent mode (never on !chat) even when everything is deployed,
        so she records/transcribes to the DB + Terminal 3 but never announces or mingles in the room until an
        operator explicitly turns chatting on.
        """
        def _silent_init() -> None:
            # Force silent-mode boot state regardless of any prior setting (belt-and-suspenders with BOT_SETTINGS defaults).
            self.kaekae_bot.settings["silent_mode"] = True
            self.kaekae_bot.settings["chat_mode"] = False
            connected = self.kaekae_bot.initialize(mark_existing_seen=True) if not self.dry_run else True
            cal_info = self.uia.auto_calibrate_camfrog()
            speaker_now = self.uia.adapter.get_active_speaker(refresh=False) if (connected and not self.dry_run) else None
            self.kaekae_bot._current_speaker = speaker_now
            if connected:
                self.emit_log(
                    f"[INCOMING MONITOR 🟢] Silent Room Listener locked onto Camfrog window '{self.uia.adapter.get_current_room() or 'Players__Lounge'}' "
                    f"(HWND={self.uia.adapter._hwnd}, Rect={self.uia.adapter._get_window_rect()}). "
                    f"Users seeded: {len(self.kaekae_bot.initial_users)} | SPEAKER_ON_MIC: {speaker_now or 'None (Mic Free)'} | "
                    f"ChatBox Pixel={cal_info.get('chat_input_screen_pt')} | TalkBtn Pixel={cal_info.get('talk_button_screen_pt')}"
                )
            else:
                self.emit_log(
                    "[INCOMING MONITOR ⏳] Waiting for Camfrog room window... (Open Camfrog 'Players__Lounge' — KaeKae_Toad will auto-attach within 2 seconds!)"
                )
            self.start_background_loop(start_spinner=False)
            # Run an initial non-intrusive component diagnostic check so the user immediately sees how every component is reacting
            self.run_full_component_diagnostics(test_mic_slice=False)

        self.run_async(_silent_init, name="SilentAutoListenInit")

    def run_full_component_diagnostics(self, *, test_mic_slice: bool = True) -> dict[str, Any]:
        """Run a full 8-component diagnostic check across Admin, Camfrog Window, Chat UIA, User List,
        SPEAKER_ON_MIC, Live Audio Input & Speech Transcription, VB-Cable Neural TTS, and SQLite 5.1/5.2 DB,
        streaming clear status lines to both Terminal 1 (Incoming) and Terminal 2 (Outgoing).
        """
        report: dict[str, Any] = {}
        try:
            if hasattr(self.uia.adapter, "probe_audio_and_component_diagnostics"):
                report = self.uia.adapter.probe_audio_and_component_diagnostics()
            else:
                report = self.uia.get_setup_diagnostics()
        except Exception as exc:
            report = {"error": str(exc)}

        admin_ok = bool(report.get("admin", True))
        conn_ok = bool(report.get("connected", False) or self.dry_run)
        hwnd_val = report.get("hwnd")
        win_title = report.get("window_title") or ("Players__Lounge (DryRun)" if self.dry_run else "Not Found")
        win_rect = report.get("window_rect") or (1273, 0, 2567, 1399)
        chat_cnt = int(report.get("chat_events_visible", 0))
        sample_chat = str(report.get("sample_chat_line", "") or "none yet")
        usr_cnt = int(report.get("user_list_count", len(self.kaekae_bot.initial_users)))
        spk_now = report.get("active_speaker") or self.kaekae_bot._current_speaker or "None (Mic Free)"
        aud_in = str(report.get("audio_input_device", "Default Input"))
        aud_out = str(report.get("audio_output_device", "CABLE Input"))
        aud_peak = int(report.get("audio_live_peak", 0))
        sr_ok = bool(report.get("speech_recognition_installed", True))
        wx_ok = bool(report.get("whisperx_installed", False))
        gpu_name = str(report.get("gpu_name", "Primary Discrete GPU"))
        gpu_backend = str(report.get("gpu_backend", "DirectML (AMD Radeon)"))
        gpu_cuda = bool(report.get("gpu_cuda_available", False))
        gpu_dml = bool(report.get("gpu_directml_available", False))
        gpu_rocm = bool(report.get("gpu_rocm_available", False))
        tts_ok = bool(report.get("edge_tts_installed", True))

        # Format GPU status label highlighting AMD Radeon RX 9070 XT DirectML / ROCm
        if gpu_dml or "DirectML" in gpu_backend or "9070" in gpu_name:
            gpu_label = f"⚡ {gpu_name} (DirectML DX12 Native AMD) ✅"
        elif gpu_rocm or "ROCm" in gpu_backend:
            gpu_label = f"⚡ {gpu_name} (ROCm AMD Native) ✅"
        elif gpu_cuda:
            gpu_label = f"⚡ {gpu_name} (NVIDIA CUDA) ✅"
        else:
            gpu_label = f"{gpu_name} ({gpu_backend})"

        speech_eng_label = (
            "WhisperX (AMD DirectML 9070 XT ⚡)"
            if (wx_ok and (gpu_dml or "DirectML" in gpu_backend))
            else (
                "WhisperX (GPU Accelerated ⚡)"
                if (wx_ok and (gpu_cuda or gpu_rocm))
                else ("WhisperX Ready" if wx_ok else ("GoogleWebSpeech" if sr_ok else "WinSpeech Fallback"))
            )
        )

        # Log Incoming-side diagnostics to Terminal 1 (Left)
        self.emit_log(
            f"[INCOMING DIAG 🩺] [1/4 WINDOW, ADMIN & GPU] Admin={'YES ✅' if admin_ok else 'NO ⚠️ (Run as Admin!)'} | "
            f"GPU={gpu_label} | "
            f"Camfrog={'LOCKED ✅' if conn_ok else 'WAITING ❌'} (HWND={hwnd_val}, Title='{win_title}', Rect={win_rect})"
        )
        self.emit_log(
            f"[INCOMING DIAG 🩺] [2/4 CHAT & USERS] Visible Chat Lines={chat_cnt} (Latest: '{sample_chat[:65]}') | "
            f"Room Users Seeded={usr_cnt} (Sample: {', '.join(report.get('sample_users', [])[:5]) or 'waiting'})"
        )
        self.emit_log(
            f"[INCOMING DIAG 🩺] [3/4 SPEAKER & LIVE TRANSCRIBE] SPEAKER_ON_MIC='{spk_now}' at {ACTIVE_SPEAKER_RECT} | "
            f"Audio Capture Device='{aud_in}' (Live Peak={aud_peak}) | SpeechEngine={speech_eng_label}"
        )

        # Optional 1.5s live microphone transcription test when user clicks "🩺 RUN FULL DIAGNOSTICS"
        if test_mic_slice and not self.dry_run and hasattr(self.uia.adapter, "transcribe_audio_chunk_for_speaker"):
            try:
                slice_res = self.uia.adapter.transcribe_audio_chunk_for_speaker(
                    duration_seconds=1.6, return_details=True
                )
                if isinstance(slice_res, dict):
                    tx_txt = str(slice_res.get("transcript", "") or "")
                    pk = int(slice_res.get("peak", 0))
                    dv = str(slice_res.get("device_name", aud_in))
                    if tx_txt:
                        self.emit_log(
                            f"[INCOMING TRANSCRIBE 📝] [LIVE MIC TEST] Heard on '{dv}' (Peak={pk}): \"{tx_txt}\""
                        )
                    else:
                        self.emit_log(
                            f"[INCOMING MIC AUDIO 🎧] [LIVE MIC TEST] Sampled 1.6s on '{dv}' -> Peak={pk} "
                            f"{'(Audio signal detected! Speak louder/clearly for text)' if pk >= 35 else '(Silent right now — waiting for someone to speak on mic)'}"
                        )
            except Exception:
                pass

        # Log Outgoing/DB-side diagnostics to Terminal 2 (Right)
        db_users = 0
        db_msgs = 0
        db_grabs = 0
        try:
            row_u = self.kaekae_bot.store._conn.execute("SELECT COUNT(*) AS c FROM users").fetchone()
            row_m = self.kaekae_bot.store._conn.execute("SELECT COUNT(*) AS c FROM chat_history").fetchone()
            row_g = self.kaekae_bot.store._conn.execute("SELECT COUNT(*) AS c FROM mic_grabs").fetchone()
            db_users = int(row_u["c"]) if row_u else 0
            db_msgs = int(row_m["c"]) if row_m else 0
            db_grabs = int(row_g["c"]) if row_g else 0
        except Exception:
            pass

        self.emit_log(
            f"[OUTGOING DIAG 🩺] [4/4 BOT TX, TTS & 5.1/5.2 DB] ChatBox Pixel={report.get('chat_box_pixel')} | "
            f"TalkBtn Pixel={report.get('talk_btn_pixel')} | VB-Cable Out='{aud_out}' (EdgeTTS={'OK ✅' if tts_ok else 'SAPI'}) | "
            f"SQLite DB: {db_users} Users, {db_msgs} Chat/Mic Lines, {db_grabs} Mic Grabs | Auto-Spin={'ON' if self.auto_spin_enabled else 'OFF'}"
        )
        report["db_users"] = db_users
        report["db_msgs"] = db_msgs
        report["db_grabs"] = db_grabs
        return report

    def deploy_all_one_click(self, *, start_auto_spin: bool = False) -> None:
        """One-Button Calibrate & Deploy:
        1. Bootstraps dependencies via `setup_env.py` in background if needed.
        2. Connects `KaeKae_Toad` (`CamfrogBot`) to the Camfrog room window, auto-calibrates the Chat Input Text Box
           and Talk Button (saves `data/camfrog_calibration.json`), and maps all 5 UIA regions.
        3. Starts KaeKae_Toad's continuous room monitor, speaker identification, and live mic transcription.
        4. Keeps Auto-Spin OFF unless `start_auto_spin=True` or the user presses Auto-Spin.
        """
        def _deploy_task() -> None:
            self.emit_log("[ONE-CLICK DEPLOY] Step 1/3: Verifying Python packages & portable directories...")
            try:
                from setup_env import bootstrap_environment
                bootstrap_environment(quiet=True, install_missing=True)
                self.emit_log("[ONE-CLICK DEPLOY] Dependencies & directories ready.")
            except Exception as exc:
                self.emit_log(f"[ONE-CLICK DEPLOY] Environment check note: {exc}")

            self.emit_log(
                f"[ONE-CLICK DEPLOY] Step 2/3: Connecting & Auto-Calibrating Camfrog Chat Text Box & Talk Button "
                f"(Chat={CHAT_WINDOW_RECT}, Input={CHAT_INPUT_RECT}, UserList={USER_LIST_RECT}, Talk={TALK_BUTTON_RECT}, Speaker={ACTIVE_SPEAKER_RECT})..."
            )
            connected = self.kaekae_bot.initialize(mark_existing_seen=True) if not self.dry_run else True
            cal_info = self.uia.auto_calibrate_camfrog()
            if connected:
                speaker_now = self.uia.adapter.get_active_speaker(refresh=False) if not self.dry_run else None
                self.kaekae_bot._current_speaker = speaker_now
                self.emit_log(
                    f"[ONE-CLICK DEPLOY] Connected & Calibrated Camfrog room! "
                    f"ChatBox Pixel={cal_info.get('chat_input_screen_pt')} | TalkBtn Pixel={cal_info.get('talk_button_screen_pt')} | "
                    f"Seeded {len(self.kaekae_bot.initial_users)} room users | SPEAKER_ON_MIC={speaker_now or 'None (Mic Free)'}."
                )
            else:
                self.emit_log(
                    f"[ONE-CLICK DEPLOY] Camfrog window status: {self.kaekae_bot.ui_automation.last_error or 'Running in background standby — will auto-attach as soon as Camfrog opens.'}"
                )

            self.emit_log(
                "[ONE-CLICK DEPLOY] Step 3/3: KaeKae_Toad Room Listener, SPEAKER_ON_MIC & Spin Analyzer active "
                "(Auto-Spin is OFF until you press '🎰 AUTO-SPIN: ON' or check '🎲 1–3m Random')."
            )
            self.start_background_loop(start_spinner=start_auto_spin)

        self.run_async(_deploy_task, name="OneClickDeployThread")

    def execute_admin_cmd(self, cmd_line: str) -> str:
        """Line 1 Handler: Emulates Administrator Command Prompt (cmd.exe / shell) and streams output to Terminal."""
        cleaned = str(cmd_line or "").strip()
        if not cleaned:
            return ""
        self.emit_log(f"[ADMIN-CMD] C:\\Windows\\System32> {cleaned}")

        def _run_shell() -> None:
            try:
                creationflags = 0x08000000 if os.name == "nt" else 0  # CREATE_NO_WINDOW on Windows
                proc = subprocess.run(
                    cleaned,
                    shell=True,
                    capture_output=True,
                    text=True,
                    timeout=30,
                    cwd=str(Path(__file__).resolve().parent),
                    creationflags=creationflags,
                )
                out = (proc.stdout or "") + (proc.stderr or "")
                lines = [ln.rstrip() for ln in out.splitlines() if ln.strip()]
                if not lines:
                    self.emit_log(f"[ADMIN-CMD] Process exited with code {proc.returncode}.")
                for ln in lines[:60]:
                    self.emit_log(f"  {ln}")
            except Exception as exc:
                self.emit_log(f"[ADMIN-CMD ERR] {exc}")

        self.run_async(_run_shell, name="AdminCmdRunner")
        return cleaned

    def send_manual_chat(self, text: str, async_dispatch: bool = False) -> bool:
        """Line 2 Handler: Talk as the bot (`KaeKae_Toad`) in Camfrog chat OR trigger internal KaeKae_Toad commands."""
        cleaned = str(text or "").strip()
        if not cleaned:
            return False

        def _do_send() -> bool:
            self.emit_log(f"[BOT-CHAT TX] KaeKae_Toad -> {cleaned}")
            lower = cleaned.lower()
            if lower.startswith("!say "):
                phrase = cleaned[5:].strip().strip('"').strip("'")
                return self.speak_on_microphone(phrase)
            if lower.startswith("!voice "):
                voice = self.uia.adapter.set_tts_voice(cleaned[7:].strip())
                self.kaekae_bot.settings["tts_voice"] = voice
                self.emit_log(f"[NEURAL-VOICE] Switched KaeKae_Toad voice to {voice}")
                return True

            # Check if KaeKae_Toad has a local trigger response for this command
            replies = self.kaekae_bot._dispatch(BOT_USERNAME, cleaned)
            if replies:
                for rep in replies:
                    self.emit_log(f"[KAEKAE-TRIGGER] {rep}")
                    self.uia.send_command(rep)
                return True

            # Otherwise send the exact text or PepeFrog game command (!spin, !join, !heist, !sheet, !bail, etc.) into Camfrog chat
            ok = self.uia.send_command(cleaned)
            if ok:
                self.emit_log(f"[BOT-CHAT SENT ✅] Dispatched '{cleaned}' + Enter into Camfrog Chat Box.")
                if lower == "!spin":
                    self._last_room_spin_mono = time.monotonic()
                    self._last_room_spin_user = BOT_USERNAME
                    self._awaiting_spin_result_until = time.monotonic() + 8.0
                    self._poll_and_record_spin_results(wait_seconds=4.2, optimal_offset_ms=self.strategy.optimal_spin_offset_ms)
            else:
                self.emit_log(f"[BOT-CHAT WARN] Could not verify chat box delivery for '{cleaned}' — check Camfrog calibration.")
            return ok

        if async_dispatch:
            self.run_async(_do_send, name="ManualChatDispatch")
            return True
        return _do_send()

    def speak_on_microphone(self, phrase: str, voice: str | None = None) -> bool:
        """Line 3 Handler: Special Microphone Broadcast Line using KaeKae_Toad's exact VB-Cable + Talk Button [1291,1169,1361,1195]
        + 1.3s Active Speaker [1506,1174,1548,1190] persistence gate logic.
        """
        cleaned = str(phrase or "").strip()
        if not cleaned:
            return False
        self.emit_log(
            f"[MIC-BROADCAST] Queueing KaeKae_Toad mic speech (Talk={TALK_BUTTON_RECT}, SpeakerGate={ACTIVE_SPEAKER_RECT} {MIC_CONFIRM_PERSIST_SECONDS}s): '{cleaned}'"
        )

        def _mic_task() -> None:
            ok = self.uia.broadcast_microphone(cleaned, voice=voice)
            if ok:
                self.emit_log(f"[MIC-BROADCAST DONE ✅] Finished speaking on Camfrog mic: '{cleaned}'")

        self.run_async(_mic_task, name="KaeKaeMicBroadcast")
        return True

    def trigger_heist_character_optimizer(self) -> str:
        """Query `!sheet` in Camfrog chat, parse the 6 D&D stats, and dispatch the optimal character upgrade command."""
        upg_cmd, reason = self.strategy.heist_advisor.recommend_character_upgrade_command()
        self.emit_log(f"[HEIST-BUILDER] {reason} -> Dispatching '!sheet' & '{upg_cmd}'")
        self.uia.send_command("!sheet")
        self.uia.send_command(upg_cmd)
        return upg_cmd

    def _process_parsed_observations(
        self,
        obs_list: list[SpinVisualObservation],
        optimal_offset_ms: int,
        *,
        spinner_user: str = "",
        measured_interval_s: float | None = None,
    ) -> bool:
        """Record any newly parsed spin/beg/jackpot observations (from KaeKae OR any user in the room)
        into StrategyEngine, CSV, and Terminal 2 (Spin & Action Analyzer).
        """
        recorded_any_spin = False
        effective_interval = measured_interval_s if (measured_interval_s is not None and measured_interval_s > 0.5) else self.spin_interval_s
        who_lbl = spinner_user or self._last_room_spin_user or BOT_USERNAME

        for obs in obs_list:
            if obs.timestamp <= self._last_recorded_obs_ts:
                continue
            self._last_recorded_obs_ts = obs.timestamp

            if obs.detected_wallet_balance is not None:
                self.strategy.wallet_balance_pat = obs.detected_wallet_balance
                self.emit_log(f"[SPIN ANALYZER 💰] Wallet Balance Update: {obs.detected_wallet_balance:,} PAT")
            if obs.detected_jackpot_pool is not None:
                self.strategy.jackpot_pool_pat = obs.detected_jackpot_pool
                self.emit_log(f"[SPIN ANALYZER 🏆] Golden Jackpot Pool: {obs.detected_jackpot_pool:,} PAT")

            if obs.outcome in {"win", "jackpot"}:
                recorded_any_spin = True
                self._awaiting_spin_result_until = 0.0
                self.strategy.record_command_execution(
                    "!spin", net_delta_pat=obs.net_delta_pat, won=True
                )
                rec = self.strategy.record_spin_timing_profit(
                    interval_seconds=effective_interval,
                    phase_offset_ms=optimal_offset_ms,
                    won=True,
                    is_jackpot=(obs.outcome == "jackpot"),
                    gross_payout_pat=obs.gross_payout_pat,
                    net_delta_pat=obs.net_delta_pat,
                )
                ev_m = self.vision.get_rolling_ev_metrics()
                self.emit_log(
                    f"[SPIN ANALYZER #{rec.spin_id} ✅] Spinner={who_lbl} | Outcome={rec.outcome} | "
                    f"Gross=+{obs.gross_payout_pat:,} PAT | Net={rec.net_delta_pat:+,} PAT | "
                    f"WinRate={ev_m.rolling_win_rate * 100:.1f}% | EV={ev_m.rolling_ev_per_spin:+.0f} PAT/spin | "
                    f"BestWindow={self.strategy.best_profit_window_bracket} | Raw='{obs.raw_text}'"
                )
                if self.announce_winnings_in_chat and obs.gross_payout_pat > 0 and who_lbl.casefold() == BOT_USERNAME.casefold():
                    win_msg = (
                        f"[KaeKae Spin #{rec.spin_id} @ {rec.interval_seconds:.1f}s] Won +{obs.gross_payout_pat:,} PAT "
                        f"(Net: {ev_m.cumulative_net_pat:+,} PAT | Jackpot: {self.vision.observed_jackpot_pool:,} PAT)!"
                    )
                    self.uia.send_command(win_msg)
            elif obs.outcome == "loss":
                recorded_any_spin = True
                self._awaiting_spin_result_until = 0.0
                self.strategy.record_command_execution(
                    "!spin", net_delta_pat=obs.net_delta_pat, won=False
                )
                rec = self.strategy.record_spin_timing_profit(
                    interval_seconds=effective_interval,
                    phase_offset_ms=optimal_offset_ms,
                    won=False,
                    is_jackpot=False,
                    gross_payout_pat=0,
                    net_delta_pat=obs.net_delta_pat,
                )
                ev_m = self.vision.get_rolling_ev_metrics()
                self.emit_log(
                    f"[SPIN ANALYZER #{rec.spin_id} ❌] Spinner={who_lbl} | Outcome=LOSS | "
                    f"Net={rec.net_delta_pat:+,} PAT | PityStreak={self.strategy.pity_state.consecutive_losses}/6 | "
                    f"WinRate={ev_m.rolling_win_rate * 100:.1f}% | EV={ev_m.rolling_ev_per_spin:+.0f} PAT/spin | "
                    f"BestWindow={self.strategy.best_profit_window_bracket} | Raw='{obs.raw_text}'"
                )
            elif obs.outcome == "cooldown":
                self.emit_log(f"[SPIN ANALYZER ⏳] Cooldown notice: '{obs.raw_text}'")
            elif obs.outcome == "beg":
                self.strategy.record_command_execution(
                    "!beg", net_delta_pat=obs.gross_payout_pat
                )
                self.emit_log(
                    f"[SPIN ANALYZER 🪙] !beg Payout: +{obs.gross_payout_pat:,} PAT | Wallet={self.strategy.wallet_balance_pat:,} PAT"
                )
        return recorded_any_spin

    def _poll_and_record_spin_results(self, *, wait_seconds: float = 3.6, optimal_offset_ms: int = 200) -> bool:
        """Poll Camfrog chat events AND OCR result region for up to `wait_seconds` after `!spin` is sent
        so asynchronous PepeFrog wheel spin outcomes are captured and logged to Terminal 2.
        """
        deadline = time.monotonic() + max(0.4, wait_seconds)
        seen_raw_lines: set[str] = set()
        recorded_spin = False

        while time.monotonic() < deadline and not self.abort_event.is_set():
            events = self.uia.poll_chat_events()
            new_lines: list[str] = []
            for e in events[-15:]:
                txt = str(e.get("text", "") or "").strip()
                usr = str(e.get("user", "") or "").strip()
                if not txt:
                    continue
                combined = f"{usr}: {txt}" if usr else txt
                if combined not in seen_raw_lines:
                    seen_raw_lines.add(combined)
                    new_lines.append(txt)

            if new_lines:
                obs_list = self.vision.parse_game_result_text(new_lines)
                if self._process_parsed_observations(obs_list, optimal_offset_ms):
                    recorded_spin = True
                    break

            time.sleep(0.35)

        # Fallback: if UIA chat nodes did not expose the PepeFrog wheel result, run Windows OCR on the chat result ROI
        if not recorded_spin and not self.dry_run:
            try:
                ocr_obs = self.vision.scan_live_screen()
                if self._process_parsed_observations(ocr_obs, optimal_offset_ms):
                    recorded_spin = True
            except Exception:
                pass

        return recorded_spin

    def step_cycle(self) -> dict[str, object]:
        """Execute a single strategic evaluation + adaptive timing UIA command dispatch + Spin Profit Recorder update."""
        optimal_offset_ms = self.vision.select_optimal_spin_offset_ms()
        self.strategy.optimal_spin_offset_ms = optimal_offset_ms
        if self.random_spin_mode:
            rolled_interval = self.strategy.roll_random_spin_interval_s(
                min_s=self.random_min_s,
                max_s=self.random_max_s,
            )
            self.spin_interval_s = rolled_interval
        else:
            self.spin_interval_s = round(20.0 + (optimal_offset_ms / 1000.0), 3)

        decision = self.strategy.evaluate_next_action()
        self.emit_log(
            f"[STRATEGY] Mode={decision.mode_flag} | Cmd={decision.command} | "
            f"Interval={self.spin_interval_s:.2f}s (Offset +{optimal_offset_ms:03d}ms) | EV={decision.expected_value_pat:+.0f} PAT | {decision.rationale}"
        )

        if decision.command == "HOLD":
            return self.strategy.export_telemetry()

        sent = self.uia.send_command(decision.command)
        if not sent:
            return self.strategy.export_telemetry()

        # Parse live visual / Camfrog chat result (or simulate realistic platform outcome in dry_run mode)
        if self.dry_run:
            self._simulate_dry_run_outcome(decision.command, optimal_offset_ms)
        else:
            if decision.command == "!spin":
                self._last_room_spin_mono = time.monotonic()
                self._last_room_spin_user = BOT_USERNAME
                self._awaiting_spin_result_until = time.monotonic() + 8.0
                self.emit_log("[SPIN MONITOR 🎰] Sent '!spin' -> Watching Camfrog chat & wheel OCR for spin result...")
            recorded_spin = self._poll_and_record_spin_results(
                wait_seconds=3.6 if decision.command == "!spin" else 1.2,
                optimal_offset_ms=optimal_offset_ms,
            )

            if decision.command == "!spin" and not recorded_spin:
                rec = self.strategy.record_spin_timing_profit(
                    interval_seconds=self.spin_interval_s,
                    phase_offset_ms=optimal_offset_ms,
                    won=False,
                    is_jackpot=False,
                    gross_payout_pat=0,
                    net_delta_pat=0,
                )
                self.emit_log(
                    f"[SPIN ANALYZER #{rec.spin_id} ⏳] Dispatched !spin @ {rec.interval_seconds:.2f}s "
                    f"({rec.window_bracket}) -> Logged to data/spin_timing_records.csv (Room monitor watching for delayed wheel payout)."
                )

            # Sync parsed !sheet stats into strategy heist advisor
            self.strategy.heist_advisor.stats = dict(self.vision.heist_state.stats)
            self.strategy.heist_advisor.unspent_points = self.vision.heist_state.unspent_stat_points
            self.strategy.heist_advisor.relics = list(self.vision.heist_state.relics_owned)

            # Auto-respond to forming heists or critical pre-vault-door !bail windows
            if self.auto_heist_enabled:
                if self.vision.heist_state.forming_job:
                    job = self.vision.heist_state.forming_job
                    self.vision.heist_state.forming_job = None
                    self.emit_log(f"[AUTO-HEIST] Detected forming '{job}' heist in Camfrog chat -> sending !join")
                    self.uia.send_command("!join")
                if self.vision.heist_state.at_vault_door_window:
                    self.vision.heist_state.at_vault_door_window = False
                    act, why = self.strategy.heist_advisor.evaluate_vault_door_vs_bail(
                        job=self.vision.heist_state.active_job or "casino",
                        accrued_loot_pat=max(25_000, self.vision.heist_state.accrued_loot_pat),
                        vault_balance_pat=self.vision.heist_state.casino_vault_pat,
                    )
                    self.emit_log(f"[HEIST VAULT DOOR] {why}")
                    if act == "!bail":
                        self.uia.send_command("!bail")

        ev_metrics = self.vision.get_rolling_ev_metrics()
        best_bracket = self.strategy.best_profit_window_bracket
        self.emit_log(
            f"[EV & TIMING] Wallet={self.strategy.wallet_balance_pat:,} PAT | "
            f"Net={ev_metrics.cumulative_net_pat:+,} PAT | "
            f"WinRate={ev_metrics.rolling_win_rate * 100:.1f}% | Best Window={best_bracket} | "
            f"Next Spin Delay={self.spin_interval_s:.1f}s"
        )
        return self.strategy.export_telemetry()

    def _simulate_dry_run_outcome(self, command: str, offset_ms: int = 200) -> None:
        cmd = command.strip().lower()
        if cmd == "!beg":
            payout = random.randint(2_200, 9_400)
            self.vision.parse_game_result_text([f"!beg payout: {payout:,} PAT"])
            self.strategy.record_command_execution("!beg", net_delta_pat=payout)
            self.emit_log(f"[SPIN ANALYZER 🪙] Simulated !beg payout: +{payout:,} PAT")
            return
        if cmd.startswith("!lotto"):
            self.strategy.record_command_execution("!lotto", net_delta_pat=-LOTTO_TICKET_COST_PAT)
            return
        if cmd == "!spin":
            win_chance = 0.72 if self.strategy.pity_state.pity_safety_net_active else 0.48
            roll = random.random()
            if roll < 0.0005:
                gross = self.strategy.jackpot_pool_pat
                net = gross - SPIN_FLAT_COST_PAT
                self.vision.parse_game_result_text([f"JACKPOT! You won {gross:,} PAT"])
                self.strategy.record_command_execution("!spin", net_delta_pat=net, won=True)
                rec = self.strategy.record_spin_timing_profit(
                    interval_seconds=self.spin_interval_s,
                    phase_offset_ms=offset_ms,
                    won=True,
                    is_jackpot=True,
                    gross_payout_pat=gross,
                    net_delta_pat=net,
                )
                self.emit_log(
                    f"[SPIN ANALYZER #{rec.spin_id} 🏆] JACKPOT HIT! +{gross:,} PAT (Net {net:+,} PAT) @ {rec.interval_seconds:.2f}s"
                )
            elif roll < win_chance:
                gross = random.choice([8_000, 10_000, 12_500, 15_000, 25_000])
                net = gross - SPIN_FLAT_COST_PAT
                self.vision.parse_game_result_text([f"You won {gross:,} PAT"])
                self.strategy.record_command_execution("!spin", net_delta_pat=net, won=True)
                rec = self.strategy.record_spin_timing_profit(
                    interval_seconds=self.spin_interval_s,
                    phase_offset_ms=offset_ms,
                    won=True,
                    is_jackpot=False,
                    gross_payout_pat=gross,
                    net_delta_pat=net,
                )
                self.emit_log(
                    f"[SPIN ANALYZER #{rec.spin_id} ✅] Outcome=WIN | Gross=+{gross:,} PAT | Net={net:+,} PAT @ {rec.interval_seconds:.2f}s ({rec.window_bracket})"
                )
            else:
                self.vision.parse_game_result_text([f"You lost {SPIN_FLAT_COST_PAT:,} PAT"])
                self.strategy.record_command_execution("!spin", net_delta_pat=-SPIN_FLAT_COST_PAT, won=False)
                rec = self.strategy.record_spin_timing_profit(
                    interval_seconds=self.spin_interval_s,
                    phase_offset_ms=offset_ms,
                    won=False,
                    is_jackpot=False,
                    gross_payout_pat=0,
                    net_delta_pat=-SPIN_FLAT_COST_PAT,
                )
                self.emit_log(
                    f"[SPIN ANALYZER #{rec.spin_id} ❌] Outcome=LOSS | Net=-{SPIN_FLAT_COST_PAT:,} PAT @ {rec.interval_seconds:.2f}s ({rec.window_bracket})"
                )

    def _kaekae_monitor_loop(self) -> None:
        """Continuous KaeKae_Toad room monitor:
        - Automatically attaches/re-attaches to the Camfrog window if Camfrog is opened after the bot starts!
        - Reads all incoming chat messages, Join/Quit presence, and moderation notices into Terminal 1.
        - Continuously updates `SPEAKER_ON_MIC` and transcribes live microphone speech directly to the front of Terminal 1.
        - Captures ALL spins sent by ANY user in the room (`!spin` + wheel outcomes) and feeds Terminal 2's Spin Analyzer!
        """
        last_reconnect_try = 0.0
        was_connected = False
        if not self.dry_run:
            was_connected = self.kaekae_bot.initialize(mark_existing_seen=True)
        last_seen_idx = len(self.kaekae_bot._recent_messages)

        while not self.abort_event.is_set():
            try:
                if not self.dry_run:
                    is_conn = bool(getattr(self.kaekae_bot.ui_automation, "is_connected", lambda: False)())
                    if not is_conn:
                        now_r = time.monotonic()
                        if (now_r - last_reconnect_try) >= 2.0:
                            last_reconnect_try = now_r
                            if self.kaekae_bot.initialize(mark_existing_seen=True):
                                is_conn = True
                                if not was_connected:
                                    was_connected = True
                                    self.emit_log(
                                        f"[INCOMING MONITOR 🟢] Attached to Camfrog room '{self.uia.adapter.get_current_room() or 'Players__Lounge'}' "
                                        f"(HWND={self.uia.adapter._hwnd}, Users={len(self.kaekae_bot.initial_users)})! Live chat & mic transcription active."
                                    )
                                last_seen_idx = len(self.kaekae_bot._recent_messages)

                    if is_conn:
                        self.kaekae_bot.poll_once()
                        recent_list = list(self.kaekae_bot._recent_messages)
                        if len(recent_list) < last_seen_idx:
                            last_seen_idx = 0
                        new_slice = recent_list[last_seen_idx:]
                        last_seen_idx = len(recent_list)

                        for latest_sender, latest_text in new_slice:
                            self.emit_log(f"[INCOMING CHAT 💬] {latest_sender}: {latest_text}")
                            low_txt = latest_text.strip().lower()

                            # Track whenever ANY user in the room types !spin so we measure inter-spin intervals & analyze all room spins
                            if low_txt == "!spin" or low_txt.startswith("!spin "):
                                now_m = time.monotonic()
                                elapsed_since_last = (now_m - self._last_room_spin_mono) if self._last_room_spin_mono > 0 else 20.2
                                self._last_room_spin_mono = now_m
                                self._last_room_spin_user = latest_sender
                                self._awaiting_spin_result_until = now_m + 7.5
                                self.emit_log(
                                    f"[SPIN ANALYZER 🎯] Detected !spin by '{latest_sender}' "
                                    f"(Δt={elapsed_since_last:.2f}s since last spin) -> Watching for wheel outcome..."
                                )

                            # Parse every incoming chat line for Spin Wins/Losses/Jackpots/Heist/Balance updates
                            obs_list = self.vision.parse_game_result_text([latest_text, f"{latest_sender}: {latest_text}"])
                            if obs_list:
                                now_m = time.monotonic()
                                measured_dt = (now_m - self._last_room_spin_mono) if self._last_room_spin_mono > 0 else self.spin_interval_s
                                self._process_parsed_observations(
                                    obs_list,
                                    self.strategy.optimal_spin_offset_ms,
                                    spinner_user=self._last_room_spin_user or latest_sender,
                                    measured_interval_s=measured_dt,
                                )

                        # If a spin was recently triggered in the room and chat UIA didn't yield the result yet, check OCR
                        if self._awaiting_spin_result_until > time.monotonic():
                            try:
                                ocr_obs = self.vision.scan_live_screen()
                                if ocr_obs:
                                    self._process_parsed_observations(
                                        ocr_obs,
                                        self.strategy.optimal_spin_offset_ms,
                                        spinner_user=self._last_room_spin_user or BOT_USERNAME,
                                    )
                            except Exception:
                                pass
            except Exception as exc:
                self.emit_log(f"[KAEKAE-POLL-ERR] {exc}")
            time.sleep(0.15)

    def start_background_loop(self, max_cycles: int | None = None, *, start_spinner: bool | None = None) -> None:
        self.abort_event.clear()
        self.kaekae_bot.running = True
        self.kaekae_bot.settings["running"] = True
        self.failsafe.start()
        if self._kaekae_thread is None or not self._kaekae_thread.is_alive():
            self._kaekae_thread = threading.Thread(
                target=self._kaekae_monitor_loop,
                name="KaeKaeToadRoomMonitor",
                daemon=True,
            )
            self._kaekae_thread.start()

        if start_spinner is not None:
            self.auto_spin_enabled = bool(start_spinner)
        if self.auto_spin_enabled:
            self.spin_stop_event.clear()
            if self._worker_thread is None or not self._worker_thread.is_alive():
                self._worker_thread = threading.Thread(
                    target=self._precision_loop,
                    args=(max_cycles,),
                    name="PepeFrogPrecisionLoop",
                    daemon=True,
                )
                self._worker_thread.start()
        else:
            self.spin_stop_event.set()
            self.next_spin_countdown_s = 0.0

    def stop(self) -> None:
        """STOP ALL BOT FUNCTIONS: Immediately halts Auto-Spin, KaeKae_Toad room monitor, mic transcription, and queued speech."""
        self.auto_spin_enabled = False
        self.spin_stop_event.set()
        self.abort_event.set()
        self.next_spin_countdown_s = 0.0
        self.kaekae_bot.kill_switch()
        self.emit_log("🚨 [STOP ALL] All KaeKae_Toad & PepeFrog bot functions, Auto-Spin, and Mic Transcription stopped immediately!")

    def _precision_loop(self, max_cycles: int | None = None) -> None:
        self.uia.connect()
        self.emit_log(
            f"[AUTO-SPIN LOOP STARTED] Sending !spin to {CHAT_INPUT_RECT} "
            f"(Click '🛑 AUTO-SPIN: OFF', uncheck '1–3m Random', or click '🚨 STOP ALL' to stop at any time)."
        )
        cycles = 0

        while not self.abort_event.is_set() and self.auto_spin_enabled and not self.spin_stop_event.is_set():
            self.step_cycle()
            cycles += 1
            if max_cycles is not None and cycles >= max_cycles:
                self.emit_log(f"[LOOP-DONE] Completed {cycles} requested cycle(s).")
                break

            next_target = time.perf_counter() + self.spin_interval_s
            while not self.abort_event.is_set() and self.auto_spin_enabled and not self.spin_stop_event.is_set():
                rem = next_target - time.perf_counter()
                self.next_spin_countdown_s = max(0.0, rem)
                if rem <= 0.060:
                    break
                time.sleep(0.040)

            if not precision_sleep_until(next_target, self.abort_event, self.spin_stop_event):
                break
            self.next_spin_countdown_s = 0.0

        self.next_spin_countdown_s = 0.0
        self.emit_log("[AUTO-SPIN LOOP EXITED] Auto-Spin worker stopped cleanly.")


# Log routing for the three vertically-stacked terminals:
#   - TERMINAL 1 (top):    INCOMING ROOM FEED (Chat, Presence, SPEAKER_ON_MIC, User DB)
#   - TERMINAL 2 (middle): BOT ACTIONS, TRIGGERS & ALL-SPINS ANALYZER (Bot Replies, EV, Timing, Strategy)
#   - TERMINAL 3 (bottom): LIVE TRANSCRIPTION (real-time [MIC] <User>: "<text>" + voice-clone progress)
_INCOMING_LOG_PREFIXES = (
    "[INCOMING",
    "[ROOM-CHAT]",
    "[ACTIVE-SPEAKER",
    "[MIC-RELEASED]",
)
# Terminal 3 tags: live spoken-word transcription AND the Coqui voice-sample/clone pipeline progress
_TRANSCRIBE_LOG_PREFIXES = (
    "[LIVE-TRANSCRIBE",
    "[MIC-TRANSCRIBE",
    "[VOICE SAMPLE",
    "[VOICE-SAMPLE",
    "[VOICE CLONE",
    "[VOICE-CLONE",
    "[CLONE ",
    "[DEFAULT ",
    "[CLR VOICE",
    "[COQUI",
    "[XTTS",
)


def is_transcription_log(msg: str) -> bool:
    """Return True if a log line belongs to Terminal 3 (Live Transcription + Voice Clone Progress)."""
    return any(tag in msg for tag in _TRANSCRIBE_LOG_PREFIXES)


def is_incoming_room_log(msg: str) -> bool:
    """Return True if a log line belongs to Terminal 1 (Incoming Room Chat, SPEAKER_ON_MIC, Presence)."""
    if is_transcription_log(msg):
        return False
    return any(tag in msg for tag in _INCOMING_LOG_PREFIXES)


def launch_desktop_gui(orchestrator: PepeFrogOrchestrator, *, auto_deploy: bool = False) -> int:
    """Launch the Native Tkinter Desktop GUI with:
    1. GUI picture (`LOGO FOR GUI.png`) stretched across the ENTIRE program GUI window (`win_w x win_h`),
       with dark translucent opacity blended into the dual terminal region so all text is crisp and readable.
    2. Automatic silent listening started on launch (no announcement in chat; Auto-Spin OFF).
    3. Dedicated `🛑 AUTO-SPIN: OFF` button + `🎰 AUTO-SPIN: ON` button + `🎲 1–3m Random` checkbox + `🚨 STOP ALL`.
    4. Cleaned trigger button decks (removed `!who is`, `!info on`, `!voices`, `!voice aria`, and all moderation buttons;
       changed `!join Crew` to `!join`).
    5. Split 2-Terminal View:
       - Terminal 1 (Left): Incoming Room Information (Chat, Presence, `SPEAKER_ON_MIC`, Live Mic Transcriptions)
       - Terminal 2 (Right): Bot Actions, Triggers & All-Spins Analyzer (`data/spin_timing_records.csv`).
    """
    from ui_automation import is_windows_admin, relaunch_as_admin

    try:
        import tkinter as tk
        from tkinter import ttk
    except Exception as exc:
        print(f"Tkinter GUI unavailable ({exc}); running in console mode.")
        orchestrator.start_silent_listening()
        try:
            while not orchestrator.abort_event.is_set():
                time.sleep(0.2)
        except KeyboardInterrupt:
            orchestrator.stop()
        return 0

    root = tk.Tk()
    admin_status = "🛡️ ADMIN MODE ACTIVE" if is_windows_admin() else "⚠️ NON-ADMIN (Click '🛡️ Relaunch as Admin' if Camfrog blocks clicks)"
    root.title(f"KaeKae_Toad & PepeFrog Command Center — Full-Window Stretched Edition ({admin_status})")
    screen_w = root.winfo_screenwidth()
    win_w = 1248 if screen_w >= 2400 else 1340
    win_h = 1365 if screen_w >= 2400 else 980
    if screen_w >= 2400:
        root.geometry(f"{win_w}x{win_h}+12+12")
    else:
        root.geometry(f"{win_w}x{win_h}")
    root.configure(bg="#060A12")

    # Load Feminine Ultra Instinct KaeKae Warrior + Crowned Gambling Frog (`LOGO FOR GUI.png`)
    # and stretch it across the ENTIRE program GUI (`win_w x win_h`), plus create translucent darkened
    # slices for the dual split terminals so the artwork shines through behind the terminal text!
    full_gui_bg_photo = None
    hero_strip_photo = None
    term_left_bg_photo = None
    term_right_bg_photo = None
    term_bottom_bg_photo = None
    wizard_logo_photo = None
    try:
        from PIL import Image, ImageEnhance, ImageOps, ImageTk

        folder = Path(__file__).resolve().parent
        for candidate in (
            folder / "LOGO FOR GUI.png",
            folder / "src" / "assets" / "images" / "kaekae_ultra_instinct_female_frog_1791731894470.jpg",
            folder / "logo_with_red_toad.jpg",
            folder / "public" / "LOGO FOR GUI.png",
            folder / "public" / "logo_with_red_toad.jpg",
            folder / "pepe_gui_banner.jpg",
        ):
            if candidate.exists():
                raw_img = Image.open(candidate).convert("RGB")
                orig_w, orig_h = raw_img.size

                # 1. Stretched & Centered Full-Window Coverage:
                # Ensure the entire GUI window (win_w x win_h) is covered seamlessly
                # so BOTH figures (the Cosmic KaeKae Warrior on the left/center and
                # the Crowned Gambling Toad on the right) are fully displayed!
                scale = max(win_w / float(orig_w), win_h / float(orig_h))
                cover_w = int(orig_w * scale)
                cover_h = int(orig_h * scale)
                cover_resized = raw_img.resize((cover_w, cover_h), Image.Resampling.LANCZOS)
                # Center crop to exact window dimensions
                offset_x = max(0, (cover_w - win_w) // 2)
                offset_y = max(0, (cover_h - win_h) // 2)
                stretched_full = cover_resized.crop((offset_x, offset_y, offset_x + win_w, offset_y + win_h))
                full_gui_bg_photo = ImageTk.PhotoImage(stretched_full)

                # 2. Top Hero Showcase strip (230px tall) showing both figures clearly with no distortion
                hero_w = win_w - 24
                hero_h = 230
                hero_backdrop = stretched_full.crop((12, 12, 12 + hero_w, 12 + hero_h))
                hero_strip_photo = ImageTk.PhotoImage(hero_backdrop)

                # 3. Translucent Opacity Terminal Backgrounds (darkened to 28% brightness with contrast boost so terminal text is 100% readable while showing both characters clearly underneath!)
                dark_full = ImageEnhance.Brightness(stretched_full).enhance(0.28)
                dark_full = ImageEnhance.Contrast(dark_full).enhance(1.15)
                half_w = max(300, (win_w - 36) // 2)
                term_h = max(320, win_h - 620)
                left_crop = dark_full.crop((12, 450, min(win_w, 12 + half_w), min(win_h, 450 + term_h)))
                right_crop = dark_full.crop((min(win_w - 10, 18 + half_w), 450, min(win_w, 18 + half_w * 2), min(win_h, 450 + term_h)))
                # Bottom slice for Terminal 3 (Live Transcription) — full-width crop of the darkened artwork.
                bottom_crop = dark_full.crop((12, min(win_h - 10, 450 + term_h // 2), min(win_w - 12, win_w), min(win_h, 450 + term_h + 180)))
                term_left_bg_photo = ImageTk.PhotoImage(left_crop)
                term_right_bg_photo = ImageTk.PhotoImage(right_crop)
                term_bottom_bg_photo = ImageTk.PhotoImage(bottom_crop)

                # 4. Wizard banner
                wiz_img = raw_img.resize((740, 210), Image.Resampling.LANCZOS)
                wizard_logo_photo = ImageTk.PhotoImage(wiz_img)
                break
    except Exception:
        pass

    # Place the full-window stretched background image across the entire root window
    if full_gui_bg_photo is not None:
        bg_label = tk.Label(root, image=full_gui_bg_photo, bd=0)
        bg_label.place(x=0, y=0, relwidth=1.0, relheight=1.0)
        bg_label.lower()

    # Variables for Method 2: Direct Pixel Coordinate Entry (Chat Box X,Y & Talk Button X,Y)
    init_chat_pt = orchestrator.uia.adapter.calibrated_chat_input_screen_pt or (1580, 1223)
    init_talk_pt = orchestrator.uia.adapter.calibrated_talk_button_screen_pt or (1326, 1182)
    chat_x_var = tk.StringVar(value=str(init_chat_pt[0]))
    chat_y_var = tk.StringVar(value=str(init_chat_pt[1]))
    talk_x_var = tk.StringVar(value=str(init_talk_pt[0]))
    talk_y_var = tk.StringVar(value=str(init_talk_pt[1]))
    live_cursor_var = tk.StringVar(value="Mouse XY: (1580, 1223)")

    def _run_cursor_calibration(status_cb: Callable[[str], None] | None = None) -> None:
        """3-Second Mouse-Hover Calibrator for the Camfrog Chat Text Box (runs on background thread)."""
        def _task() -> None:
            for remaining in (3, 2, 1):
                msg = f"🎯 Hover your mouse cursor INSIDE the Camfrog 'Say something...' chat box now... Locking in {remaining}s!"
                orchestrator.emit_log(f"[CALIBRATE CHAT] {msg}")
                if status_cb is not None:
                    root.after(0, lambda m=msg: status_cb(m))
                time.sleep(1.0)
            payload = orchestrator.uia.calibrate_chat_input_from_cursor(delay_seconds=0.0)
            pt = payload.get("chat_input_screen_pt") or [1946, 1223]
            root.after(0, lambda: (chat_x_var.set(str(pt[0])), chat_y_var.set(str(pt[1]))))
            done_msg = f"✅ Locked Camfrog Chat Text Box at Screen Pixel {pt}! Saved to data/camfrog_calibration.json."
            orchestrator.emit_log(f"[CALIBRATE CHAT] {done_msg}")
            if status_cb is not None:
                root.after(0, lambda m=done_msg: status_cb(m))

        orchestrator.run_async(_task, name="CursorCalibrateChatThread")

    def _run_talk_button_cursor_calibration(status_cb: Callable[[str], None] | None = None) -> None:
        """3-Second Mouse-Hover Calibrator for the Camfrog Talk Button so KaeKae_Toad can grab the mic directly by pixel."""
        def _task() -> None:
            for remaining in (3, 2, 1):
                msg = f"🎙️ Hover your mouse cursor OVER the Camfrog 'Talk' Button now... Locking in {remaining}s!"
                orchestrator.emit_log(f"[CALIBRATE TALK] {msg}")
                if status_cb is not None:
                    root.after(0, lambda m=msg: status_cb(m))
                time.sleep(1.0)
            payload = orchestrator.uia.calibrate_talk_button_from_cursor(delay_seconds=0.0)
            tpt = payload.get("talk_button_screen_pt") or [1326, 1182]
            root.after(0, lambda: (talk_x_var.set(str(tpt[0])), talk_y_var.set(str(tpt[1]))))
            done_msg = f"✅ Locked Camfrog Talk Button at Screen Pixel {tpt}! Saved to data/camfrog_calibration.json — KaeKae_Toad will grab mic here!"
            orchestrator.emit_log(f"[CALIBRATE TALK] {done_msg}")
            if status_cb is not None:
                root.after(0, lambda m=done_msg: status_cb(m))

        orchestrator.run_async(_task, name="CursorCalibrateTalkThread")

    def _apply_direct_pixel_calibration(status_cb: Callable[[str], None] | None = None) -> None:
        """Method 2: Enter exact (X, Y) pixel coordinates straight in for Chat Text Box and Talk Button."""
        def _task() -> None:
            try:
                cx = int(chat_x_var.get().strip())
                cy = int(chat_y_var.get().strip())
            except Exception:
                cx, cy = 1946, 1223
            try:
                tx = int(talk_x_var.get().strip())
                ty = int(talk_y_var.get().strip())
            except Exception:
                tx, ty = 1326, 1182

            orchestrator.uia.set_direct_pixel_calibration(
                chat_x=cx,
                chat_y=cy,
                talk_x=tx,
                talk_y=ty,
            )
            msg = (
                f"📌 [METHOD 2 PIXEL LOCK SAVED] Chat Box Pixel=({cx}, {cy}) | Talk Button Pixel=({tx}, {ty}) "
                f"-> Saved to data/camfrog_calibration.json!"
            )
            orchestrator.emit_log(msg)
            if status_cb is not None:
                root.after(0, lambda m=msg: status_cb(m))

        orchestrator.run_async(_task, name="DirectPixelCalibrateThread")

    def _open_setup_wizard() -> None:
        """Interactive 4-Step First-Time Setup & 2560x1440 Right-Half Camfrog Verification Wizard (100% Non-Blocking)."""
        wiz = tk.Toplevel(root)
        wiz.title("🧭 Interactive First-Time Setup, Direct Pixel Entry & Talk/Chat Calibration Wizard")
        wiz.geometry("820x800+120+40")
        wiz.configure(bg="#09060A")
        wiz.transient(root)

        if wizard_logo_photo is not None:
            lbl_img = tk.Label(wiz, image=wizard_logo_photo, bg="#09060A", bd=0)
            lbl_img.pack(pady=(10, 4))

        tk.Label(
            wiz,
            text="KAEKAE_TOAD & PEPEFROG — 4-STEP SETUP, CHAT BOX & TALK BUTTON PIXEL CALIBRATION",
            bg="#09060A",
            fg="#EF4444",
            font=("Segoe UI", 12, "bold"),
        ).pack(pady=(2, 2))

        diag_var = tk.StringVar(value="Loading live Camfrog diagnostics in background...")
        diag_box = tk.Label(
            wiz,
            textvariable=diag_var,
            bg="#140A10",
            fg="#E2E8F0",
            font=("Consolas", 9),
            justify="left",
            anchor="w",
            padx=12,
            pady=10,
            relief="groove",
        )
        diag_box.pack(fill="x", padx=16, pady=6)

        def _refresh_wizard_diag_async(prefix_note: str = "") -> None:
            def _bg_diag() -> None:
                d = orchestrator.uia.get_setup_diagnostics()
                deps_str = " ".join(f"{k}:{'OK' if v else 'MISSING'}" for k, v in d["dependencies"].items())
                lines = [
                    f"{prefix_note}" if prefix_note else "=== LIVE 2560×1440 RIGHT-HALF, CHAT BOX & TALK BUTTON PIXEL REPORT ===",
                    f"[STEP 1] Dependencies : {deps_str}",
                    f"[STEP 2] Camfrog Lock : {'CONNECTED' if d['connected'] else 'WAITING FOR CAMFROG'} | HWND={d['hwnd']} | Title='{d['window_title']}'",
                    f"         Window Rect  : {d['window_rect']} (2560×1440 Right-Half Match: {'YES' if d['is_right_half_2560x1440'] else 'AUTO-SCALED'})",
                    f"         Chat Box Pt  : Pixel={d.get('calibrated_chat_input_screen_pt')} | Rect={d['scaled_chat_input_rect']}",
                    f"         Talk Btn Pt  : Pixel={d.get('calibrated_talk_button_screen_pt')} | Rect={d['scaled_talk_button_rect']} | Gate={d['scaled_active_speaker_rect']} (1.3s)",
                ]
                text_out = "\n".join(lines)
                root.after(0, lambda: diag_var.set(text_out))

            orchestrator.run_async(_bg_diag, name="WizardDiagRefresh")

        _refresh_wizard_diag_async()

        steps_frame = tk.Frame(wiz, bg="#09060A", padx=16)
        steps_frame.pack(fill="both", expand=True)

        s2 = tk.Frame(steps_frame, bg="#140A10", pady=6, padx=10)
        s2.pack(fill="x", pady=3)
        tk.Label(
            s2,
            text="Calibrate Chat Box & Talk Button (Method 1: Auto/3s Hover OR Method 2: Enter Pixel X,Y Straight In)",
            bg="#140A10",
            fg="#FBBF24",
            font=("Segoe UI", 9, "bold"),
            anchor="w",
        ).pack(fill="x")
        s2_btns = tk.Frame(s2, bg="#140A10")
        s2_btns.pack(anchor="w", pady=(4, 2))
        make_rounded_btn(
            s2_btns,
            text="🎯 3s Hover Chat Box",
            bg="#EF4444",
            fg="#FFFFFF",
            font=("Segoe UI", 9, "bold"),
            padx=8,
            pady=4,
            command=lambda: _run_cursor_calibration(_refresh_wizard_diag_async),
        ).pack(side="left", padx=(0, 6))
        make_rounded_btn(
            s2_btns,
            text="🎙️ 3s Hover Talk Button",
            bg="#10B981",
            fg="#022C22",
            font=("Segoe UI", 9, "bold"),
            padx=8,
            pady=4,
            command=lambda: _run_talk_button_cursor_calibration(_refresh_wizard_diag_async),
        ).pack(side="left", padx=(0, 6))
        make_rounded_btn(
            s2_btns,
            text="Close Wizard",
            bg="#334155",
            fg="#FFFFFF",
            font=("Segoe UI", 9, "bold"),
            padx=10,
            pady=4,
            command=wiz.destroy,
        ).pack(side="left")

    # 1. TOP BAR: ONE-CLICK CALIBRATE, CALIBRATE CHAT/TALK, !SPIN ONCE, AUTO-SPIN ON, AUTO-SPIN: OFF BUTTON, 1-3M RANDOM & STOP ALL
    top_bar = tk.Frame(root, bg="#0B0F19", pady=4, padx=8, highlightthickness=1, highlightbackground="#EF4444")
    top_bar.pack(fill="x", padx=10, pady=(4, 2))

    # NOTE: `make_rounded_btn` is the module-level RoundedButton factory (true rounded corners).
    make_rounded_btn(
        top_bar,
        text="⚡ ONE-CLICK DEPLOY",
        bg="#EF4444",
        fg="#FFFFFF",
        activebackground="#F87171",
        highlightbackground="#F87171",
        font=("Segoe UI", 8, "bold"),
        padx=7,
        pady=3,
        command=lambda: orchestrator.deploy_all_one_click(start_auto_spin=False),
    ).pack(side="left", padx=(0, 3))

    make_rounded_btn(
        top_bar,
        text="🩺 RUN FULL DIAGNOSTICS",
        bg="#8B5CF6",
        fg="#FFFFFF",
        activebackground="#A78BFA",
        highlightbackground="#A78BFA",
        font=("Segoe UI", 8, "bold"),
        padx=7,
        pady=3,
        command=lambda: orchestrator.run_async(lambda: orchestrator.run_full_component_diagnostics(test_mic_slice=True), name="FullDiagRun"),
    ).pack(side="left", padx=(0, 3))

    make_rounded_btn(
        top_bar,
        text="🎯 CALIBRATE CHAT (3s)",
        bg="#F59E0B",
        fg="#090D16",
        activebackground="#FBBF24",
        highlightbackground="#FBBF24",
        font=("Segoe UI", 8, "bold"),
        padx=6,
        pady=3,
        command=lambda: _run_cursor_calibration(),
    ).pack(side="left", padx=(0, 3))

    make_rounded_btn(
        top_bar,
        text="🎙️ CALIBRATE TALK (3s)",
        bg="#10B981",
        fg="#022C22",
        activebackground="#34D399",
        highlightbackground="#34D399",
        font=("Segoe UI", 8, "bold"),
        padx=6,
        pady=3,
        command=lambda: _run_talk_button_cursor_calibration(),
    ).pack(side="left", padx=(0, 3))

    make_rounded_btn(
        top_bar,
        text="🧭 WIZARD",
        bg="#0284C7",
        fg="#FFFFFF",
        activebackground="#38BDF8",
        highlightbackground="#38BDF8",
        font=("Segoe UI", 8, "bold"),
        padx=6,
        pady=3,
        command=_open_setup_wizard,
    ).pack(side="left", padx=(0, 3))

    make_rounded_btn(
        top_bar,
        text="🎰 !SPIN ONCE",
        bg="#10B981",
        fg="#022C22",
        activebackground="#34D399",
        highlightbackground="#34D399",
        font=("Segoe UI", 8, "bold"),
        padx=7,
        pady=3,
        command=lambda: orchestrator.run_async(orchestrator.step_cycle, name="ManualSpinNow"),
    ).pack(side="left", padx=(0, 3))

    random_mode_var = tk.BooleanVar(value=False)

    btn_autospin_on = make_rounded_btn(
        top_bar,
        text="🎰 START AUTO-SPIN",
        bg="#059669",
        fg="#FFFFFF",
        activebackground="#10B981",
        highlightbackground="#10B981",
        font=("Segoe UI", 8, "bold"),
        padx=7,
        pady=3,
    )
    btn_autospin_off = make_rounded_btn(
        top_bar,
        text="🛑 AUTO-SPIN: OFF",
        bg="#B91C1C",
        fg="#FFFFFF",
        activebackground="#EF4444",
        highlightbackground="#EF4444",
        font=("Segoe UI", 8, "bold"),
        padx=7,
        pady=3,
    )

    def _sync_autospin_ui() -> None:
        if orchestrator.auto_spin_enabled:
            mode_tag = "1-3m RND" if orchestrator.random_spin_mode else "20.2s"
            btn_autospin_on.config(text=f"🎰 AUTO-SPIN: ON ({mode_tag})", bg="#10B981", fg="#022C22")
            btn_autospin_off.config(text="🛑 SET AUTO-SPIN: OFF", bg="#EF4444", fg="#FFFFFF")
        else:
            btn_autospin_on.config(text="🎰 START AUTO-SPIN", bg="#334155", fg="#F8FAFC")
            btn_autospin_off.config(text="🛑 AUTO-SPIN: OFF", bg="#1E293B", fg="#94A3B8")

    def _on_click_start_autospin() -> None:
        if not random_mode_var.get():
            random_mode_var.set(True)
            orchestrator.random_spin_mode = True
        orchestrator.set_auto_spin_state(True, random_1_to_3_min=bool(random_mode_var.get()))
        _sync_autospin_ui()

    def _on_click_autospin_off() -> None:
        random_mode_var.set(False)
        orchestrator.set_auto_spin_state(False, random_1_to_3_min=False)
        _sync_autospin_ui()

    btn_autospin_on.config(command=_on_click_start_autospin)
    btn_autospin_on.pack(side="left", padx=(0, 3))

    btn_autospin_off.config(command=_on_click_autospin_off)
    btn_autospin_off.pack(side="left", padx=(0, 3))

    def _on_toggle_random_checkbox() -> None:
        checked = bool(random_mode_var.get())
        orchestrator.set_auto_spin_state(checked, random_1_to_3_min=checked)
        _sync_autospin_ui()

    chk_random = tk.Checkbutton(
        top_bar,
        text="🎲 1–3m Random",
        variable=random_mode_var,
        command=_on_toggle_random_checkbox,
        bg="#0B0F19",
        fg="#FBBF24",
        selectcolor="#1E293B",
        activebackground="#0B0F19",
        activeforeground="#FBBF24",
        font=("Consolas", 8, "bold"),
    )
    chk_random.pack(side="left", padx=(2, 4))

    def _do_stop_all() -> None:
        random_mode_var.set(False)
        orchestrator.run_async(orchestrator.stop, name="StopAllBotFunctions")
        root.after(50, _sync_autospin_ui)

    make_rounded_btn(
        top_bar,
        text="🚨 STOP ALL",
        bg="#DC2626",
        fg="#FFFFFF",
        activebackground="#EF4444",
        font=("Segoe UI", 8, "bold"),
        padx=8,
        pady=3,
        command=_do_stop_all,
    ).pack(side="right")

    if not is_windows_admin():
        make_rounded_btn(
            top_bar,
            text="🛡️ ADMIN",
            bg="#7C3AED",
            fg="#FFFFFF",
            font=("Segoe UI", 8, "bold"),
            padx=5,
            pady=3,
            command=lambda: root.destroy() if relaunch_as_admin() else None,
        ).pack(side="right", padx=(0, 4))

    # 1B. SECOND CALIBRATION METHOD BAR: DIRECT PIXEL COORDINATE ENTRY (Chat Box X,Y + Talk Button X,Y + Live Mouse XY)
    pixel_bar = tk.Frame(root, bg="#0F172A", pady=2, padx=8, highlightthickness=1, highlightbackground="#334155")
    pixel_bar.pack(fill="x", padx=10, pady=(0, 2))

    tk.Label(
        pixel_bar,
        text="📌 METHOD 2 (DIRECT PIXELS):",
        bg="#0F172A",
        fg="#FBBF24",
        font=("Consolas", 8, "bold"),
    ).pack(side="left", padx=(0, 4))

    tk.Label(pixel_bar, text="Chat X:", bg="#0F172A", fg="#38BDF8", font=("Consolas", 8, "bold")).pack(side="left")
    tk.Entry(pixel_bar, textvariable=chat_x_var, width=5, bg="#030712", fg="#38BDF8", insertbackground="#38BDF8", font=("Consolas", 8)).pack(side="left", padx=2)
    tk.Label(pixel_bar, text="Y:", bg="#0F172A", fg="#38BDF8", font=("Consolas", 8, "bold")).pack(side="left")
    tk.Entry(pixel_bar, textvariable=chat_y_var, width=5, bg="#030712", fg="#38BDF8", insertbackground="#38BDF8", font=("Consolas", 8)).pack(side="left", padx=(2, 6))

    tk.Label(pixel_bar, text="Talk Btn X:", bg="#0F172A", fg="#34D399", font=("Consolas", 8, "bold")).pack(side="left")
    tk.Entry(pixel_bar, textvariable=talk_x_var, width=5, bg="#030712", fg="#34D399", insertbackground="#34D399", font=("Consolas", 8)).pack(side="left", padx=2)
    tk.Label(pixel_bar, text="Y:", bg="#0F172A", fg="#34D399", font=("Consolas", 8, "bold")).pack(side="left")
    tk.Entry(pixel_bar, textvariable=talk_y_var, width=5, bg="#030712", fg="#34D399", insertbackground="#34D399", font=("Consolas", 8)).pack(side="left", padx=(2, 6))

    make_rounded_btn(
        pixel_bar,
        text="💾 LOCK PIXELS",
        bg="#0284C7",
        fg="#FFFFFF",
        font=("Segoe UI", 8, "bold"),
        padx=6,
        pady=1,
        command=lambda: _apply_direct_pixel_calibration(),
    ).pack(side="left", padx=(0, 4))

    make_rounded_btn(
        pixel_bar,
        text="🎙️ TEST TALK BTN",
        bg="#059669",
        fg="#FFFFFF",
        font=("Segoe UI", 8, "bold"),
        padx=6,
        pady=1,
        command=lambda: orchestrator.speak_on_microphone("KaeKae Toad testing calibrated Talk Button pixel coordinate."),
    ).pack(side="left", padx=(0, 4))

    tk.Label(
        pixel_bar,
        textvariable=live_cursor_var,
        bg="#0F172A",
        fg="#E2E8F0",
        font=("Consolas", 8, "bold"),
    ).pack(side="right")

    # 2. HERO BANNER SHOWCASE (Displays the Feminine Ultra Instinct KaeKae Warrior + Crowned Gambling Frog artwork)
    hero_canvas = tk.Canvas(
        root,
        width=win_w - 24,
        height=240,
        bg="#090508",
        highlightthickness=1,
        highlightbackground="#EF4444",
    )
    hero_canvas.pack(padx=10, pady=2, fill="x", expand=False)
    if hero_strip_photo is not None:
        hero_canvas.create_image((win_w - 24) // 2, 120, anchor="center", image=hero_strip_photo)
    else:
        hero_canvas.create_text(
            (win_w - 24) // 2,
            120,
            text="KAEKAE_TOAD & PEPEFROG SUPREME COMMAND GUI",
            fill="#EF4444",
            font=("Consolas", 16, "bold"),
        )

    # HUD Telemetry + Dynamic SPEAKER_ON_MIC + Spin Profit Recorder Bar
    hud_var = tk.StringVar(
        value="🟢 KAEKAE LISTENING (AUTO-SPIN: OFF) | 🎙️ SPEAKER_ON_MIC: None (Mic Free) | Wallet: 25,000 PAT | Jackpot: 2,850,000 PAT | Spins Analyzed: 0"
    )
    hud_label = tk.Label(
        root,
        textvariable=hud_var,
        bg="#0F172A",
        fg="#34D399",
        font=("Consolas", 9, "bold"),
        anchor="w",
        padx=10,
        pady=3,
    )
    hud_label.pack(fill="x", padx=10, pady=(0, 2))

    # 3. CLEANED INTERACTIVE TRIGGER BUTTON DECKS
    # Removed buttons per user request (while keeping all triggers active in Camfrog chat!):
    #   - Removed: !who is, !info on, !voices, !voice aria, and ALL moderation buttons (!unpunish, !unblockmic, !unban, !topic, !watchlist, who kicked, who banned, who punished)
    #   - Changed: '!join Crew' -> '!join'
    decks_frame = tk.Frame(root, bg="#060A12")
    decks_frame.pack(fill="x", padx=10, pady=1)

    def _make_btn_row(parent: tk.Widget, label_text: str, fg_color: str, commands: list[tuple[str, str]]) -> None:
        row = tk.Frame(parent, bg="#0B1120", pady=2, padx=6)
        row.pack(fill="x", pady=1)
        tk.Label(
            row,
            text=label_text,
            bg="#0B1120",
            fg=fg_color,
            font=("Consolas", 8, "bold"),
            width=22,
            anchor="w",
        ).pack(side="left")
        for btn_label, cmd_str in commands:
            make_rounded_btn(
                row,
                text=btn_label,
                bg="#1E293B",
                fg="#F8FAFC",
                activebackground="#334155",
                activeforeground="#34D399",
                highlightbackground="#334155",
                highlightthickness=1,
                relief="flat",
                bd=0,
                cursor="hand2",
                font=("Consolas", 8, "bold"),
                padx=6,
                pady=2,
                command=lambda c=cmd_str: orchestrator.send_manual_chat(c, async_dispatch=True),
            ).pack(side="left", padx=2)

    _make_btn_row(
        decks_frame,
        "🐸 KAEKAE_TOAD TRIGGERS:",
        "#34D399",
        [
            ("!chat", "!chat"),
            ("!chatoff", "!chatoff"),
            ("!shutup", "!shutup"),
            ("!transcribe", "!transcribe"),
            ("!transcribed", "!transcribed"),
            ("!suppress", "!suppress"),
            ("!unsuppress", "!unsuppress"),
            ("!grabs 24h", "!grabs 24h"),
            ("!diss", "!diss the room"),
            ("!idk", "!idk what is the jackpot"),
            ("!happy", "!happy"),
            ("!sad", "!sad"),
            ("!mad", "!mad"),
            ("!triggers", "!triggers"),
            ("Next Page (-)", "-"),
            ("!say Hello", "!say KaeKae Toad live on the microphone"),
            ("!admins", "!admins"),
        ],
    )

    _make_btn_row(
        decks_frame,
        "🔫 !HEIST & STRONGEST CHAR:",
        "#FBBF24",
        [
            ("!sheet", "!sheet"),
            ("!heist store", "!heist store"),
            ("!heist casino", "!heist casino"),
            ("!heist convoy", "!heist convoy"),
            ("!heist bank", "!heist bank"),
            ("!join", "!join"),
            ("!bail (+20%)", "!bail"),
            ("!defend", "!defend"),
            ("!allot INT", "!allot int"),
            ("!allot DEX", "!allot dex"),
            ("!allot CON", "!allot con"),
            ("!ring INT", "!ring int"),
            ("!reroll CHA", "!reroll cha"),
            ("!shop", "!shop"),
            ("!buy lawyer", "!buy lawyer 1"),
            ("!buy ghost", "!buy ghost 1"),
            ("!buy lockpick", "!buy lockpick 2"),
            ("!gear", "!gear"),
        ],
    )

    _make_btn_row(
        decks_frame,
        "🎰 PEPEFROG GAMES (#cat-games):",
        "#38BDF8",
        [
            ("!spin (5k)", "!spin"),
            ("!balance", "!balance"),
            ("!lotto quick", "!lotto quick"),
            ("!bingo start", "!bingo start"),
            ("!bingo buy 4", "!bingo buy 4"),
            ("!bingo CALL!", "!bingo"),
            ("!trivia 1000", "!trivia 1000"),
            ("!showdown", "!showdown"),
            ("!guess 5000", "!guess 5000"),
            ("!arena 5000", "!arena 5000"),
            ("!brawl", "!brawl Stonerwayne1000 2500"),
            ("!duel", "!duel Stonerwayne1000 1000"),
            ("!bj 1000", "!bet 1000"),
            ("!holdem", "!holdem start 50/100"),
        ],
    )

    # 4. THREE VERTICALLY-STACKED TERMINALS (one on top of each other) OVER THE STRETCHED GUI ARTWORK:
    #    - TERMINAL 1 (top):    INCOMING ROOM FEED (Chat, Presence, SPEAKER_ON_MIC, User DB)
    #    - TERMINAL 2 (middle): BOT ACTIONS, TRIGGERS & ALL-SPINS ANALYZER (Every !spin in room, EV, Timing, Replies)
    #    - TERMINAL 3 (bottom): LIVE TRANSCRIPTION (real-time [MIC] <User>: "<text>") + Coqui Voice Clone Progress
    split_terminals = tk.Frame(root, bg="#060A12")
    split_terminals.pack(fill="both", expand=True, padx=10, pady=3)
    split_terminals.grid_columnconfigure(0, weight=1)
    split_terminals.grid_rowconfigure(0, weight=3, uniform="term_rows")
    split_terminals.grid_rowconfigure(1, weight=3, uniform="term_rows")
    split_terminals.grid_rowconfigure(2, weight=2, uniform="term_rows")

    # --- TERMINAL 1 (TOP): INCOMING ROOM INFORMATION ---
    term1_frame = tk.Frame(split_terminals, bg="#050811", highlightthickness=1, highlightbackground="#10B981")
    term1_frame.grid(row=0, column=0, sticky="nsew", pady=(0, 3))

    term1_header = tk.Frame(term1_frame, bg="#06281E", padx=8, pady=2)
    term1_header.pack(fill="x")
    tk.Label(
        term1_header,
        text="📥 TERMINAL 1: INCOMING ROOM FEED (CHAT • SPEAKER_ON_MIC • PRESENCE • USER DB)",
        bg="#06281E",
        fg="#34D399",
        font=("Consolas", 8, "bold"),
        anchor="w",
    ).pack(side="left")

    term1_body = tk.Frame(term1_frame, bg="#050811")
    term1_body.pack(fill="both", expand=True)
    if term_left_bg_photo is not None:
        t1_bg = tk.Label(term1_body, image=term_left_bg_photo, bd=0)
        t1_bg.place(x=0, y=0, relwidth=1.0, relheight=1.0)

    term1_scroll = tk.Scrollbar(term1_body, orient="vertical")
    term1_text = tk.Listbox(
        term1_body,
        height=10,
        bg="#070B14",
        fg="#A7F3D0",
        font=("Consolas", 9),
        selectbackground="#064E3B",
        highlightthickness=0,
        bd=0,
        yscrollcommand=term1_scroll.set,
    )
    term1_scroll.config(command=term1_text.yview)
    term1_scroll.pack(side="right", fill="y")
    term1_text.pack(side="left", fill="both", expand=True, padx=4, pady=2)

    # --- TERMINAL 2 (MIDDLE): BOT ACTIONS, TRIGGERS & ALL-SPINS ANALYZER ---
    term2_frame = tk.Frame(split_terminals, bg="#050811", highlightthickness=1, highlightbackground="#EF4444")
    term2_frame.grid(row=1, column=0, sticky="nsew", pady=(3, 3))

    term2_header = tk.Frame(term2_frame, bg="#280910", padx=8, pady=2)
    term2_header.pack(fill="x")
    tk.Label(
        term2_header,
        text="📤 TERMINAL 2: BOT ACTIONS, TRIGGERS & ALL-SPINS ANALYZER (data/spin_timing_records.csv)",
        bg="#280910",
        fg="#FBBF24",
        font=("Consolas", 8, "bold"),
        anchor="w",
    ).pack(side="left")

    term2_body = tk.Frame(term2_frame, bg="#050811")
    term2_body.pack(fill="both", expand=True)
    if term_right_bg_photo is not None:
        t2_bg = tk.Label(term2_body, image=term_right_bg_photo, bd=0)
        t2_bg.place(x=0, y=0, relwidth=1.0, relheight=1.0)

    term2_scroll = tk.Scrollbar(term2_body, orient="vertical")
    term2_text = tk.Listbox(
        term2_body,
        height=10,
        bg="#0A0710",
        fg="#FDE68A",
        font=("Consolas", 9),
        selectbackground="#3B0764",
        highlightthickness=0,
        bd=0,
        yscrollcommand=term2_scroll.set,
    )
    term2_scroll.config(command=term2_text.yview)
    term2_scroll.pack(side="right", fill="y")
    term2_text.pack(side="left", fill="both", expand=True, padx=4, pady=2)

    # --- TERMINAL 3 (BOTTOM): LIVE TRANSCRIPTION + VOICE CLONE PROGRESS ---
    term3_frame = tk.Frame(split_terminals, bg="#050811", highlightthickness=1, highlightbackground="#38BDF8")
    term3_frame.grid(row=2, column=0, sticky="nsew", pady=(3, 0))

    term3_header = tk.Frame(term3_frame, bg="#0A1E2E", padx=8, pady=2)
    term3_header.pack(fill="x")
    tk.Label(
        term3_header,
        text="🎙️ TERMINAL 3: LIVE TRANSCRIPTION (real-time [MIC] <User>: \"<text>\") • VOICE SAMPLE / CLONE PROGRESS",
        bg="#0A1E2E",
        fg="#38BDF8",
        font=("Consolas", 8, "bold"),
        anchor="w",
    ).pack(side="left")

    term3_body = tk.Frame(term3_frame, bg="#050811")
    term3_body.pack(fill="both", expand=True)
    if term_bottom_bg_photo is not None:
        t3_bg = tk.Label(term3_body, image=term_bottom_bg_photo, bd=0)
        t3_bg.place(x=0, y=0, relwidth=1.0, relheight=1.0)
    term3_scroll = tk.Scrollbar(term3_body, orient="vertical")
    term3_text = tk.Listbox(
        term3_body,
        height=8,
        bg="#060E1A",
        fg="#7DD3FC",
        font=("Consolas", 9),
        selectbackground="#075985",
        highlightthickness=0,
        bd=0,
        yscrollcommand=term3_scroll.set,
    )
    term3_scroll.config(command=term3_text.yview)
    term3_scroll.pack(side="right", fill="y")
    term3_text.pack(side="left", fill="both", expand=True, padx=4, pady=2)

    def _push_terminal(listbox: "tk.Listbox", msg: str, max_lines: int = 400) -> None:
        """Append one line to a terminal Listbox, auto-scroll, and trim to keep it responsive."""
        listbox.insert("end", msg)
        if listbox.size() > max_lines:
            listbox.delete(0)
        listbox.see("end")

    # Try applying native Windows layered window translucency (96% opacity) so the desktop/background blends smoothly
    if os.name == "nt":
        try:
            root.attributes("-alpha", 0.97)
        except Exception:
            pass

    # 5. THREE DEDICATED INPUT LINES (1: Admin CMD Line, 2: Bot Chat Line, 3: Special Mic Broadcast Line)
    inputs_container = tk.Frame(root, bg="#0B1120", padx=10, pady=5, highlightthickness=1, highlightbackground="#334155")
    inputs_container.pack(fill="x", padx=10, pady=(0, 6))

    # LINE 1: Administrator Command Prompt (cmd.exe) Emulator Line
    row_cmd = tk.Frame(inputs_container, bg="#0B1120", pady=1)
    row_cmd.pack(fill="x")
    tk.Label(
        row_cmd,
        text="1) ADMIN CMD LINE (C:\\Windows\\System32>):",
        bg="#0B1120",
        fg="#38BDF8",
        font=("Consolas", 9, "bold"),
        width=40,
        anchor="w",
    ).pack(side="left")
    cmd_entry = tk.Entry(row_cmd, bg="#030712", fg="#38BDF8", insertbackground="#38BDF8", font=("Consolas", 10))
    cmd_entry.pack(side="left", fill="x", expand=True, ipady=2, padx=6)

    def _submit_admin_cmd(_event: object = None) -> None:
        val = cmd_entry.get().strip()
        if val:
            cmd_entry.delete(0, "end")
            orchestrator.execute_admin_cmd(val)

    cmd_entry.bind("<Return>", _submit_admin_cmd)
    make_rounded_btn(
        row_cmd,
        text="Run Admin CMD",
        bg="#0284C7",
        fg="#FFFFFF",
        font=("Segoe UI", 8, "bold"),
        padx=10,
        command=_submit_admin_cmd,
    ).pack(side="left")

    # LINE 2: Talk as Bot in Camfrog Chat Line (Non-blocking background dispatch)
    row_chat = tk.Frame(inputs_container, bg="#0B1120", pady=1)
    row_chat.pack(fill="x")
    tk.Label(
        row_chat,
        text="2) BOT CHAT LINE (Send to Camfrog Chat):",
        bg="#0B1120",
        fg="#FBBF24",
        font=("Consolas", 9, "bold"),
        width=40,
        anchor="w",
    ).pack(side="left")
    chat_entry = tk.Entry(row_chat, bg="#030712", fg="#F8FAFC", insertbackground="#FBBF24", font=("Consolas", 10))
    chat_entry.pack(side="left", fill="x", expand=True, ipady=2, padx=6)

    def _submit_bot_chat(_event: object = None) -> None:
        val = chat_entry.get().strip()
        if val:
            chat_entry.delete(0, "end")
            orchestrator.send_manual_chat(val, async_dispatch=True)

    chat_entry.bind("<Return>", _submit_bot_chat)
    make_rounded_btn(
        row_chat,
        text="Send as Bot in Chat",
        bg="#F59E0B",
        fg="#090D16",
        font=("Segoe UI", 8, "bold"),
        padx=10,
        command=_submit_bot_chat,
    ).pack(side="left")

    # LINE 3: Special KaeKae_Toad Microphone Broadcast Line (VB-Cable + 3 fast clicks & hold Talk + 1.3s Speaker Gate)
    row_mic = tk.Frame(inputs_container, bg="#0B1120", pady=1)
    row_mic.pack(fill="x")
    tk.Label(
        row_mic,
        text="3) SPECIAL MIC LINE (Speak on Camfrog Mic):",
        bg="#0B1120",
        fg="#34D399",
        font=("Consolas", 9, "bold"),
        width=40,
        anchor="w",
    ).pack(side="left")
    mic_entry = tk.Entry(row_mic, bg="#030712", fg="#34D399", insertbackground="#34D399", font=("Consolas", 10))
    mic_entry.pack(side="left", fill="x", expand=True, ipady=2, padx=6)

    # --- SPECIAL MIC LINE voice engine sub-menu (Local Kokoro GPU / Coqui XTTS-v2 / TTS EDGE) ---
    # Default to the local Kokoro GPU engine when its ONNX assets are present; else Edge Neural.
    _kokoro_ready = False
    try:
        _kokoro_ready = bool(orchestrator.uia.adapter.kokoro.is_available())
    except Exception:
        _kokoro_ready = False
    engine_var = tk.StringVar(value="Local GPU (Kokoro)" if _kokoro_ready else "TTS EDGE")
    voice_var = tk.StringVar(value="Edge Aria")
    engine_menu = ttk.Combobox(
        row_mic,
        textvariable=engine_var,
        values=["Local GPU (Kokoro)", "TTS EDGE", "Coqui (XTTS v2)"],
        width=15,
        state="readonly",
    )
    engine_menu.pack(side="left", padx=(0, 4))
    voice_menu = ttk.Combobox(
        row_mic,
        textvariable=voice_var,
        values=edge_female_voice_catalog(),
        width=22,
        state="readonly",
    )
    voice_menu.pack(side="left", padx=(0, 6))

    def _refresh_voice_menu(*_args: object) -> None:
        """Repoint the voice sub-menu at the selected engine.

        * Local GPU (Kokoro): women-only Kokoro presets + Kokoro Default (Test).
        * Coqui (XTTS v2): women + Default/CLONE last (live clone-slot state).
        * TTS EDGE: women-only Edge Neural presets.
        """
        eng = engine_var.get()
        if eng.startswith("Local GPU"):
            values = kokoro_voice_catalog()
        elif eng.startswith("Coqui"):
            values = coqui_voice_catalog()
            # Replace the dynamic clone slot label with its live state (Active vs None).
            clone_label = orchestrator.uia.adapter.coqui.clone_slot_label()
            values = [clone_label if v == COQUI_CLONE_VOICE else v for v in values]
        else:
            values = edge_female_voice_catalog()
        voice_menu.configure(values=values)
        if voice_var.get() not in values:
            voice_var.set(values[0])

    engine_menu.bind("<<ComboboxSelected>>", _refresh_voice_menu)
    _refresh_voice_menu()

    def _submit_mic_speech(_event: object = None) -> None:
        val = mic_entry.get().strip()
        if val:
            mic_entry.delete(0, "end")
            orchestrator.speak_on_microphone(val, voice=voice_var.get())

    mic_entry.bind("<Return>", _submit_mic_speech)
    make_rounded_btn(
        row_mic,
        text="🎙️ Speak on Mic (VB-Cable)",
        bg="#10B981",
        fg="#022C22",
        font=("Segoe UI", 8, "bold"),
        padx=10,
        command=_submit_mic_speech,
    ).pack(side="left")

    # --- Coqui voice cloning buttons: Sample -> Clone -> Default -> CLR Voice (progress streams to Terminal 3) ---
    row_voice_ops = tk.Frame(inputs_container, bg="#0B1120", pady=1)
    row_voice_ops.pack(fill="x")
    tk.Label(
        row_voice_ops,
        text="   🧬 COQUI VOICE CLONE:",
        bg="#0B1120",
        fg="#A78BFA",
        font=("Consolas", 9, "bold"),
        width=40,
        anchor="w",
    ).pack(side="left")

    def _voice_sample_action() -> None:
        def _task() -> None:
            orchestrator.uia.adapter.coqui.capture_voice_sample(log=orchestrator.emit_log)
            root.after(0, _refresh_voice_menu)
        orchestrator.run_async(_task, name="VoiceSampleCapture")

    def _voice_clone_action() -> None:
        def _task() -> None:
            ok, _ref = orchestrator.uia.adapter.coqui.clone_active_voice(log=orchestrator.emit_log)

            def _sync_menu() -> None:
                engine_var.set("Coqui (XTTS v2)")
                _refresh_voice_menu()
                if ok:
                    voice_var.set(orchestrator.uia.adapter.coqui.clone_slot_label())
            root.after(0, _sync_menu)
        orchestrator.run_async(_task, name="CoquiVoiceClone")

    def _voice_default_action() -> None:
        def _task() -> None:
            if orchestrator.uia.adapter.coqui.set_clone_as_default(log=orchestrator.emit_log):

                def _sync_menu() -> None:
                    engine_var.set("Coqui (XTTS v2)")
                    _refresh_voice_menu()
                    voice_var.set(orchestrator.uia.adapter.coqui.clone_slot_label())
                root.after(0, _sync_menu)
        orchestrator.run_async(_task, name="SetCloneDefault")

    def _voice_clear_action() -> None:
        def _task() -> None:
            if orchestrator.uia.adapter.coqui.clear_default_voice(log=orchestrator.emit_log):

                def _sync_menu() -> None:
                    engine_var.set("Coqui (XTTS v2)")
                    _refresh_voice_menu()
                    voice_var.set(COQUI_DEFAULT_VOICE)
                root.after(0, _sync_menu)
        orchestrator.run_async(_task, name="ClearCloneVoice")

    for btn_text, btn_bg, btn_cmd in (
        ("🎙️ Sample", "#8B5CF6", _voice_sample_action),
        ("🧬 Clone Voice", "#6366F1", _voice_clone_action),
        ("▶️ Default", "#10B981", _voice_default_action),
        ("🧹 CLR Voice", "#DC2626", _voice_clear_action),
    ):
        make_rounded_btn(
            row_voice_ops,
            text=btn_text,
            bg=btn_bg,
            fg="#FFFFFF",
            activebackground="#F8FAFC",
            activeforeground="#0B1120",
            highlightbackground=btn_bg,
            highlightthickness=1,
            relief="flat",
            bd=0,
            cursor="hand2",
            font=("Segoe UI", 8, "bold"),
            padx=8,
            pady=2,
            command=btn_cmd,
        ).pack(side="left", padx=2)

    tk.Label(
        row_voice_ops,
        text="Sample → Clone → Default broadcasts the clone; CLR Voice reverts to Coqui Default (Test Clone).",
        bg="#0B1120",
        fg="#64748B",
        font=("Consolas", 7),
        anchor="w",
    ).pack(side="left", padx=(8, 0))

    def _on_log(msg: str) -> None:
        def _append() -> None:
            if is_transcription_log(msg):
                _push_terminal(term3_text, msg)
            elif is_incoming_room_log(msg):
                _push_terminal(term1_text, msg)
            else:
                _push_terminal(term2_text, msg)
        root.after(0, _append)

    orchestrator.add_log_listener(_on_log)

    def _refresh_hud() -> None:
        if os.name == "nt":
            try:
                from ctypes import wintypes
                pt = wintypes.POINT()
                if ctypes.windll.user32.GetCursorPos(ctypes.byref(pt)):
                    live_cursor_var.set(f"Live Mouse XY: ({int(pt.x)}, {int(pt.y)})")
            except Exception:
                pass
        tel = orchestrator.strategy.export_telemetry()
        recs = tel.get("recent_spin_records", [])
        total_spins = tel.get("total_spins_executed", len(recs))
        monitor_alive = orchestrator._kaekae_thread is not None and orchestrator._kaekae_thread.is_alive() and not orchestrator.abort_event.is_set()
        spin_alive = orchestrator.auto_spin_enabled and not orchestrator.spin_stop_event.is_set() and not orchestrator.abort_event.is_set()
        speaker_now = orchestrator.kaekae_bot._current_speaker or "None (Mic Free)"
        tx_chat = "CHAT-ON" if orchestrator.kaekae_bot.settings.get("post_transcripts_to_chat", False) else "SILENT-DB"

        if spin_alive:
            state_badge = "🎰 AUTO-SPIN: ON"
        elif monitor_alive:
            state_badge = "🟢 KAEKAE LISTENING (AUTO-SPIN: OFF)"
        else:
            state_badge = "⏸️ STOPPED"

        _sync_autospin_ui()
        hud_var.set(
            f"{state_badge} | 🎙️ SPEAKER_ON_MIC: {speaker_now} (MicLog:{tx_chat}) | "
            f"Wallet: {tel['wallet_balance_pat']:,} PAT ({tel['net_profit_pat']:+,}) | "
            f"Jackpot: {tel['jackpot_pool_pat']:,} PAT | "
            f"Next !spin: {orchestrator.next_spin_countdown_s:.1f}s | "
            f"Spins Analyzed: {total_spins}"
        )
        root.after(200, _refresh_hud)

    root.after(200, _refresh_hud)

    # Start KaeKae_Toad's room listener automatically on GUI launch (with NO chat announcement, and Auto-Spin OFF)!
    orchestrator.emit_log(
        "[INCOMING MONITOR 🟢] Automatic silent room listener starting on launch (no announcement in chat). "
        "Recording all users, attributes, speech patterns, genders, biographies & SPEAKER_ON_MIC to SQLite DB."
    )
    orchestrator.emit_log(
        "[SPIN ANALYZER 🎰] Auto-Spin is OFF on launch. All room spins (!spin) are automatically captured & analyzed here in Terminal 2. "
        "Click '🎰 START AUTO-SPIN' to spin or '🛑 AUTO-SPIN: OFF' to stop spinning while KaeKae keeps running."
    )
    root.after(180, orchestrator.start_silent_listening)

    root.mainloop()
    orchestrator.stop()
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="KaeKae_Toad & PepeFrog Unified Desktop GUI & Precision Orchestrator")
    parser.add_argument("--dry-run", action="store_true", help="Simulate UIA & Vision outcomes without sending hardware keystrokes")
    parser.add_argument("--cycles", type=int, default=None, help="Run a fixed number of spin cycles and exit")
    parser.add_argument("--interval", type=float, default=PRECISION_SPIN_INTERVAL_S, help="Precision cooldown interval in seconds (default: 20.2)")
    parser.add_argument("--fixed-interval", action="store_true", help="Use fixed 20.2s interval instead of 1-3 minute randomized spin interval")
    parser.add_argument("--gui", action="store_true", help="Launch the Desktop GUI (default unless --cli or --cycles is passed)")
    parser.add_argument("--cli", action="store_true", help="Run in headless CLI mode instead of opening the Desktop GUI")
    parser.add_argument("--auto-start", action="store_true", help="Auto-connect KaeKae_Toad monitor on GUI launch (default)")
    parser.add_argument("--no-auto-start", action="store_true", help="Open GUI without auto-starting")
    parser.add_argument("--dump-telemetry", action="store_true", help="Run one strategic evaluation and print JSON telemetry")
    args, _ = parser.parse_known_args(argv)

    orchestrator = PepeFrogOrchestrator(
        dry_run=args.dry_run,
        spin_interval_s=args.interval,
        random_spin_mode=False,
        auto_spin_enabled=False,
    )

    if args.dump_telemetry:
        print(json.dumps(orchestrator.strategy.export_telemetry(), indent=2))
        return 0

    # Launch the Desktop GUI by default unless headless --cli or --cycles is explicitly requested!
    if args.gui or (not args.cli and args.cycles is None):
        return launch_desktop_gui(orchestrator, auto_deploy=not args.no_auto_start)

    # Headless CLI mode starts KaeKae_Toad silent room listener (and spinner only if --cycles is passed)
    orchestrator.start_silent_listening()
    if args.cycles is not None:
        orchestrator.set_auto_spin_state(True, random_1_to_3_min=not args.fixed_interval)
        orchestrator.start_background_loop(max_cycles=args.cycles, start_spinner=True)
    while orchestrator._kaekae_thread is not None and orchestrator._kaekae_thread.is_alive():
        try:
            if args.cycles is not None and (orchestrator._worker_thread is None or not orchestrator._worker_thread.is_alive()):
                break
            time.sleep(0.05)
        except KeyboardInterrupt:
            orchestrator.stop()
            break
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
