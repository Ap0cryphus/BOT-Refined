#!/usr/bin/env python3
"""
Second terminal script to monitor all information from Camfrog rooms.
Uses the fixed Desktop(backend="uia") connection and calibrated coordinates:
- Chat Window Pane(50033) / Text(50020): [l=1281,t=170,r=2355,b=1160]
- Chat Txt Field Pane(50033): [l=1396,t=1206,r=2497,b=1241]
- User List(50008): [l=2359,t=141,r=2559,b=1160] (trending [l=2359,r=2559], filtering VIEWING # & LURKERS #)
- Talk Button(50000): [l=1291,t=1169,r=1361,b=1195]
- Active Speaker Button(50000): [l=1506,t=1174,r=1548,b=1190] (KaeKae_Toad 1.3s persistence)
"""

import os
import sys
import threading
import time
from datetime import datetime

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from config import ACTIVE_SPEAKER_RECT, BOT_USERNAME, CHAT_WINDOW_RECT, USER_LIST_RECT
from ui_automation import CamfrogUIAutomation


class RoomMonitor:
    """Monitors all room activity and provides detailed live logging."""

    def __init__(self):
        self.ui_automation = CamfrogUIAutomation()
        self.current_room = None
        self.monitoring = False
        self._seen = set()
        self._last_speaker = None
        self._speaker_since = 0.0

    def get_current_room(self):
        return self.ui_automation.get_current_room()

    def monitor_rooms(self):
        print("Starting room monitoring...")
        print(f"  Chat Window:    {CHAT_WINDOW_RECT}")
        print(f"  User List:      {USER_LIST_RECT} (trending [l=2359, r=2559])")
        print(f"  Active Speaker: {ACTIVE_SPEAKER_RECT} (Bot='{BOT_USERNAME}')")
        print("Press Ctrl+C to stop monitoring")

        if not self.ui_automation.connect_to_camfrog():
            print(f"Error connecting: {self.ui_automation.last_error}")
            return

        initial_users = self.ui_automation.get_user_list(refresh=True)
        print(f"[STARTUP ROSTER] {len(initial_users)} users in room: {', '.join(initial_users[:20])}")

        try:
            while True:
                current_room = self.get_current_room()
                if current_room != self.current_room:
                    print(f"\n[ROOM CHANGE] Now in: {current_room}")
                    self.current_room = current_room

                speaker = self.ui_automation.get_active_speaker(refresh=True)
                now = time.monotonic()
                if speaker != self._last_speaker:
                    timestamp = datetime.now().strftime("%H:%M:%S")
                    if self._last_speaker:
                        held = max(0.1, now - self._speaker_since)
                        print(f"[{timestamp}] [MIC FREE] {self._last_speaker} left mic after {held:.1f}s ({ACTIVE_SPEAKER_RECT} cleared)")
                    if speaker:
                        print(f"[{timestamp}] [ON MIC] {speaker} at {ACTIVE_SPEAKER_RECT}")
                    self._last_speaker = speaker
                    self._speaker_since = now if speaker else 0.0

                events = self.ui_automation.get_chat_events()
                for event in events:
                    key = (
                        event.get("kind"),
                        event.get("action", ""),
                        event.get("user", ""),
                        event.get("text", ""),
                        event.get("timestamp", ""),
                    )
                    if key in self._seen:
                        continue
                    self._seen.add(key)
                    timestamp = datetime.now().strftime("%H:%M:%S")
                    if event["kind"] == "message":
                        print(f"[{timestamp}] [{current_room or 'Players__Lounge'}] {event['user']}: {event['text']}")
                    elif event["kind"] == "presence":
                        action = "JOINED" if event["action"] == "join" else "LEFT"
                        print(f"[{timestamp}] [{current_room or 'Players__Lounge'}] User {event['user']} {action}")

                time.sleep(0.4)

        except KeyboardInterrupt:
            print("\nMonitoring stopped by user.")
        except Exception as e:
            print(f"Error during monitoring: {e}")


def main():
    print("Starting Camfrog Room Monitor")
    print("=" * 40)
    monitor = RoomMonitor()
    monitor_thread = threading.Thread(target=monitor.monitor_rooms, daemon=True)
    monitor_thread.start()
    try:
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        print("\nExiting room monitor...")
        sys.exit(0)


if __name__ == "__main__":
    main()
