#!/usr/bin/env python3
"""
Second terminal script to monitor all information from Camfrog rooms.
This script will show incoming events from all rooms and help setup logic/instructions on the data.
"""

import sys
import os
import time
import threading
from datetime import datetime

# Add the project root to the path so we can import modules
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from ui_automation import CamfrogUIAutomation
from camfrog_bot import CamfrogBot

class RoomMonitor:
    """Monitors all room activity and provides detailed logging."""
    
    def __init__(self):
        self.ui_automation = CamfrogUIAutomation()
        self.current_room = None
        self.monitoring = False
        
    def get_current_room(self):
        """Get the current room by position detection."""
        return self.ui_automation.get_current_room()
        
    def monitor_rooms(self):
        """Monitor room activity and log information."""
        print("Starting room monitoring...")
        print("Press Ctrl+C to stop monitoring")
        
        try:
            while True:
                # Get current room
                current_room = self.get_current_room()
                if current_room != self.current_room:
                    print(f"\n[ROOM CHANGE] Now in: {current_room}")
                    self.current_room = current_room
                
                # Get chat events and log them
                events = self.ui_automation.get_chat_events()
                
                for event in events:
                    timestamp = datetime.now().strftime("%H:%M:%S")
                    if event["kind"] == "message":
                        print(f"[{timestamp}] [{current_room or 'Unknown'}] {event['user']}: {event['text']}")
                    elif event["kind"] == "presence":
                        action = "JOINED" if event["action"] == "join" else "LEFT"
                        print(f"[{timestamp}] [{current_room or 'Unknown'}] User {event['user']} {action}")
                
                time.sleep(0.5)
                
        except KeyboardInterrupt:
            print("\nMonitoring stopped by user.")
        except Exception as e:
            print(f"Error during monitoring: {e}")

def main():
    """Main function to start the room monitor."""
    print("Starting Camfrog Room Monitor")
    print("=" * 40)
    
    monitor = RoomMonitor()
    
    # Start monitoring in a separate thread
    monitor_thread = threading.Thread(target=monitor.monitor_rooms, daemon=True)
    monitor_thread.start()
    
    try:
        # Keep main thread alive
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        print("\nExiting room monitor...")
        sys.exit(0)

if __name__ == "__main__":
    main()