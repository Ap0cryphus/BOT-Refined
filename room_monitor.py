#!/usr/bin/env python3
"""
Second terminal script to monitor all information from Camfrog rooms.
Uses the fixed Desktop(backend="uia") connection and calibrated coordinates:
- Chat Window Pane(50033) / Text(50020): [l=1281,t=170,r=2355,b=1160]
- Chat Txt Field Pane(50033): [l=1396,t=1206,r=2497,b=1241]
- User List List(50008): [l=2359,t=141,r=2559,b=1160] (reads 'USERS (#)' count + usernames, filters VIEWING # / LURKERS #)
- Talk Button Button(50000): [l=1291,t=1169,r=1361,b=1195] (2 clicks + hold)
- Active Speaker Button(50000): [l=1506,t=1174,r=1548,b=1190] (KaeKae_Toad 1.3s persistence gate)
"""

import json
import sys
import time
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

from camfrog_bot import CamfrogBot, detect_moderation
from config import (
    ACTIVE_SPEAKER_RECT,
    CHAT_INPUT_RECT,
    CHAT_WINDOW_RECT,
    POLL_INTERVAL_SECONDS,
    ROOM_TAB_CLICK_POINTS,
    TALK_BUTTON_RECT,
    USER_LIST_RECT,
)
from ui_automation import CamfrogUIAutomation


class RoomMonitor:
    """Monitors and displays all room information in a terminal while also dispatching bot triggers (!triggers, !who is, etc.)."""

    def __init__(self, *, dry_run: bool = False):
        self.bot = CamfrogBot(dry_run=dry_run)
        self.ui_automation = self.bot.ui_automation
        self.store = self.bot.store
        self.running = False
        self._last_snapshot_sigs: list[str] = []
        self._last_status_print_mono: float = 0.0
        self._last_speaker: str | None = "__init__"

    def start_monitoring(self) -> bool:
        print("=== CAMFROG ROOM MONITOR + BOT TRIGGER PIPELINE ===")
        print("Connecting to Camfrog...")
        if not self.bot.initialize(mark_existing_seen=True):
            print(f"ERROR: Could not connect to Camfrog: {self.ui_automation.last_error}")
            return False

        # Reuse the cached UIA snapshot from initialize() so startup is instant
        initial_events = self.ui_automation.get_chat_events()
        self._last_snapshot_sigs = [self._event_sig(e) for e in initial_events]

        print("Connected to Camfrog successfully!")
        initial_users = self.bot.initial_users
        user_count = self.ui_automation.get_user_count(refresh=False)
        print(
            f"Initial Room Roster [l={USER_LIST_RECT[0]},r={USER_LIST_RECT[2]}] "
            f"(USERS (#): {user_count} | Listed: {len(initial_users)}): "
            f"{', '.join(initial_users[:15])}"
        )
        print(
            f"Ultra-fast polling active (every {POLL_INTERVAL_SECONDS:.2f}s) + live bot triggers enabled "
            f"(!triggers, !who is, !info on, !say, etc.) -> Chat Input {CHAT_INPUT_RECT}.\n"
        )
        self.running = True

        try:
            while self.running:
                self._display_room_info()
                time.sleep(max(0.05, POLL_INTERVAL_SECONDS))
        except KeyboardInterrupt:
            print("\nMonitoring stopped by user.")
            self.running = False

        return True

    @staticmethod
    def _event_sig(event: dict[str, str]) -> str:
        return f"{event.get('kind', '')}:{event.get('action', '')}:{event.get('user', '')}:{event.get('text', '')}:{event.get('timestamp', '')}"

    @classmethod
    def _diff_new_tail_events(cls, prev_sigs: list[str], curr_events: list[dict[str, str]]) -> list[dict[str, str]]:
        """Return only the newly appended events at the bottom of the chat window (even if identical to an older line)."""
        curr_sigs = [cls._event_sig(e) for e in curr_events]
        if not prev_sigs:
            return curr_events
        if curr_sigs == prev_sigs:
            return []
        # Find the longest suffix of prev_sigs (or slice of prev_sigs) that matches a prefix of the tail of curr_sigs
        max_overlap = min(len(prev_sigs), len(curr_sigs))
        for k in range(max_overlap, 0, -1):
            if prev_sigs[-k:] == curr_sigs[:k]:
                return curr_events[k:]
        # Also check if curr_sigs contains the last 3 items of prev_sigs near the end
        anchor_len = min(3, len(prev_sigs))
        anchor = prev_sigs[-anchor_len:]
        for idx in range(len(curr_sigs) - anchor_len, -1, -1):
            if curr_sigs[idx:idx + anchor_len] == anchor:
                return curr_events[idx + anchor_len:]
        # Fallback: return any event whose signature was not in prev_sigs
        prev_set = set(prev_sigs)
        return [e for e, s in zip(curr_events, curr_sigs) if s not in prev_set]

    def _display_room_info(self) -> None:
        timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        # Force a fresh UIA snapshot each cycle (now ~0.08s without slow COM legacy probes)
        self.ui_automation.nodes(refresh=True)
        self.bot._track_active_speaker()
        current_room = self.ui_automation.get_current_room()
        speaker = self.ui_automation.get_active_speaker(refresh=False)
        users = self.ui_automation.get_user_list(refresh=False)
        users_header_count = self.ui_automation.get_user_count(refresh=False)

        events = self.ui_automation.get_chat_events()
        new_events = self._diff_new_tail_events(self._last_snapshot_sigs, events)
        if events:
            self._last_snapshot_sigs = [self._event_sig(e) for e in events]

        for event in new_events:
            event_key = f"{self._event_sig(event)}:{time.monotonic():.3f}"
            if event.get("kind") == "presence":
                self.store.record_presence(event.get("user", ""), event.get("action", "join"), event_key)
            elif event.get("kind") == "message":
                self.bot._handle_message(event.get("user", ""), event.get("text", ""), event.get("timestamp", ""))

        self.bot._run_scheduled_disses()

        now_mono = time.monotonic()
        speaker_changed = speaker != self._last_speaker
        # Print immediately when new chat/presence events arrive or active speaker changes, or every 2.0s as a heartbeat
        if not new_events and not speaker_changed and (now_mono - self._last_status_print_mono) < 2.0:
            return

        self._last_status_print_mono = now_mono
        self._last_speaker = speaker

        # Prefer the sum of the 3 User List headers (YOU ARE VIEWING + MEMBERS + LURKERS) / Users (#) count
        effective_count = users_header_count if users_header_count > 0 else (len(users) or self.store.active_user_count())
        print(
            f"[{timestamp}] Room: {current_room or 'Unknown'} | "
            f"Users: {effective_count} (Listed: {len(users)}, Active Tracked: {self.store.active_user_count()}) | "
            f"Mic @ {ACTIVE_SPEAKER_RECT}: {speaker or 'FREE (erased)'}"
        )

        if new_events:
            print(f"  New Events ({len(new_events)}) from Chat Window {CHAT_WINDOW_RECT}:")
            for event in new_events[-15:]:
                event_type = event.get("kind", "unknown")
                user = event.get("user", "unknown")
                text = event.get("text", "")
                ts = event.get("timestamp", "")

                if event_type == "message":
                    print(f"    [MSG] {ts} {user}: {text}")
                    moderation = detect_moderation(text)
                    if moderation:
                        print(f"    [MOD] {moderation['actor']} {moderation['action']} {moderation['target']}")
                elif event_type == "presence":
                    action = event.get("action", "unknown")
                    dur_sec = self.store.user_chat_duration_seconds(user)
                    verb = "joined" if action == "join" else "quit"
                    print(f"    [PRESENCE] {user} {verb} the room (tracked duration: {dur_sec:.0f}s)")

        print("-" * 72)


def main():
    monitor = RoomMonitor()
    monitor.start_monitoring()


if __name__ == "__main__":
    main()
