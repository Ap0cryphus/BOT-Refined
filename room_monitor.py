#!/usr/bin/env python3
"""
Second terminal script to monitor all information from Camfrog rooms.
Uses the fixed Desktop(backend="uia") connection and calibrated coordinates.
"""

import os
import sys
import threading
import time
from datetime import datetime

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from ui_automation import CamfrogUIAutomation


class RoomMonitor:
    """Monitors all room activity and provides detailed logging."""

    def __init__(self):
        self.ui_automation = CamfrogUIAutomation()
        self.current_room = None
        self.monitoring = False
        self._seen = set()

    def get_current_room(self):
        return self.ui_automation.get_current_room()

    def monitor_rooms(self):
        print("Starting room monitoring...")
        print("Press Ctrl+C to stop monitoring")

        if not self.ui_automation.connect_to_camfrog():
            print(f"Error connecting: {self.ui_automation.last_error}")
            return

        try:
            while True:
                current_room = self.get_current_room()
                if current_room != self.current_room:
                    print(f"\n[ROOM CHANGE] Now in: {current_room}")
                    self.current_room = current_room

                speaker = self.ui_automation.get_active_speaker()
                events = self.ui_automation.get_chat_events()

                for event in events:
                    key = (event.get("kind"), event.get("action", ""), event.get("user", ""), event.get("text", ""), event.get("timestamp", ""))
                    if key in self._seen:
                        continue
                    self._seen.add(key)
                    timestamp = datetime.now().strftime("%H:%M:%S")
                    if event["kind"] == "message":
                        print(f"[{timestamp}] [{current_room or 'Players__Lounge'}] {event['user']}: {event['text']}")
                    elif event["kind"] == "presence":
                        action = "JOINED" if event["action"] == "join" else "LEFT"
                        print(f"[{timestamp}] [{current_room or 'Players__Lounge'}] User {event['user']} {action}")

                if speaker:
                    pass  # Active speaker tracked right of Talk Button [1291,1169,1361,1195]

                time.sleep(0.5)

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
