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

from camfrog_bot import CamfrogStore, detect_moderation
from config import (
    ACTIVE_SPEAKER_RECT,
    CHAT_INPUT_RECT,
    CHAT_WINDOW_RECT,
    ROOM_TAB_CLICK_POINTS,
    TALK_BUTTON_RECT,
    USER_LIST_RECT,
)
from ui_automation import CamfrogUIAutomation


class RoomMonitor:
    """Monitors and displays all room information in a second terminal."""

    def __init__(self):
        self.ui_automation = CamfrogUIAutomation()
        self.store = CamfrogStore()
        self.running = False
        self.last_events: set[str] = set()

    def start_monitoring(self) -> bool:
        print("=== CAMFROG ROOM MONITOR (CALIBRATED UIA PIPELINE) ===")
        print("Connecting to Camfrog...")
        if not self.ui_automation.connect_to_camfrog():
            print(f"ERROR: Could not connect to Camfrog: {self.ui_automation.last_error}")
            return False

        print("Connected to Camfrog successfully!")
        print(f"Locations: {json.dumps(self.ui_automation.layout_locations())}")
        initial_users = self.ui_automation.get_user_list(refresh=False)
        user_count = self.ui_automation.get_user_count(refresh=False)
        self.store.seed_initial_users(initial_users)
        print(
            f"Initial Room Roster [l={USER_LIST_RECT[0]},r={USER_LIST_RECT[2]}] "
            f"(USERS (#): {user_count} | Listed: {len(initial_users)}): "
            f"{', '.join(initial_users[:15])}"
        )
        print("Monitoring room activities... Press Ctrl+C to stop.\n")
        self.running = True

        try:
            while self.running:
                self._display_room_info()
                time.sleep(2.0)
        except KeyboardInterrupt:
            print("\nMonitoring stopped by user.")
            self.running = False

        return True

    def _display_room_info(self) -> None:
        timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        # Force a fresh UIA snapshot each cycle so Active Speaker, USERS (#), and Chat are up to date
        self.ui_automation.nodes(refresh=True)
        current_room = self.ui_automation.get_current_room()
        speaker = self.ui_automation.get_active_speaker(refresh=False)
        users = self.ui_automation.get_user_list(refresh=False)
        users_header_count = self.ui_automation.get_user_count(refresh=False)

        events = self.ui_automation.get_chat_events()
        new_events = []
        for event in events:
            event_key = f"{event.get('kind', '')}:{event.get('user', '')}:{event.get('text', '')}:{event.get('timestamp', '')}"
            if event_key not in self.last_events:
                self.last_events.add(event_key)
                new_events.append(event)
                if event.get("kind") == "presence":
                    self.store.record_presence(event.get("user", ""), event.get("action", "join"), event_key)
                elif event.get("kind") == "message":
                    self.store.record_message(event.get("user", ""), event.get("text", ""), event.get("timestamp", ""))

        effective_count = max(users_header_count, len(users), self.store.active_user_count())
        print(
            f"[{timestamp}] Room: {current_room or 'Unknown'} | "
            f"Users: {effective_count} (Listed: {len(users)}, Active Tracked: {self.store.active_user_count()}) | "
            f"Mic @ {ACTIVE_SPEAKER_RECT}: {speaker or 'FREE (erased)'}"
        )

        if new_events:
            print(f"  New Events ({len(new_events)}) from Chat Window {CHAT_WINDOW_RECT}:")
            for event in new_events[-10:]:
                event_type = event.get("kind", "unknown")
                user = event.get("user", "unknown")
                text = event.get("text", "")
                ts = event.get("timestamp", "")

                if event_type == "message":
                    print(f"    [MSG] {ts} {user}: {text}")
                    moderation = detect_moderation(text)
                    if moderation:
                        self.store.record_moderation(moderation, text)
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
