#!/usr/bin/env python3
"""
Process information from different Camfrog rooms using calibrated coordinates:
- (1390, 50) -> Room List
- (1550, 50) -> Players__Lounge
- Chat Window Pane(50033)/Text(50020): [l=1281,t=170,r=2355,b=1160]
- Chat Txt Field Pane(50033): [l=1396,t=1206,r=2497,b=1241]
- User List(50008): [l=2359,t=141,r=2559,b=1160] (trending [l=2359,r=2559], max 100)
- Talk Button(50000): [l=1291,t=1169,r=1361,b=1195]
- Active Speaker Button(50000): [l=1506,t=1174,r=1548,b=1190]
"""

import os
import sys
from datetime import datetime

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from ui_automation import CamfrogUIAutomation


class RoomDataProcessor:
    """Process data from different rooms and set up logic based on room context."""

    def __init__(self):
        self.ui_automation = CamfrogUIAutomation()
        self.room_commands = {
            "Players__Lounge": [r"!players", r"!lounge", r"!room info"],
            "Drama_Central": [r"!drama", r"!central", r"!showtime"],
            "Room List": [r"!rooms", r"!list", r"!switch"],
        }
        self.room_triggers = {
            "Players__Lounge": {
                "trigger_words": ["game", "play", "match"],
                "response_template": "@{user} Let's play some games in the lounge!",
                "action": "send_to_room",
            },
            "Drama_Central": {
                "trigger_words": ["drama", "argument", "fight"],
                "response_template": "@{user} This is a drama central - keep it civil!",
                "action": "send_to_room",
            },
        }

    def process_message(self, room_name, user, message):
        print(f"[{room_name}] {user}: {message}")
        message_lower = message.lower()
        if message_lower.startswith("!"):
            self.handle_command(room_name, user, message)
        if room_name in self.room_triggers:
            trigger_config = self.room_triggers[room_name]
            for trigger_word in trigger_config["trigger_words"]:
                if trigger_word in message_lower:
                    response = trigger_config["response_template"].format(user=user)
                    print(f"  -> Triggered: {response}")
                    return response
        return None

    def handle_command(self, room_name, user, message):
        print(f"  Command detected in {room_name}: {message}")

    def get_room_context(self, room_name):
        users = self.ui_automation.get_user_list()
        return {
            "room": room_name,
            "timestamp": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            "active_users": users,
            "user_count": len(users),
            "active_speaker": self.ui_automation.get_active_speaker(),
            "message_count": len(self.ui_automation.get_chat_events()),
        }


def main():
    print("Camfrog Room Data Processor")
    print("=" * 40)
    processor = RoomDataProcessor()
    for room, user, message in [
        ("Players__Lounge", "Alice", "!players"),
        ("Players__Lounge", "Bob", "Let's play a game!"),
        ("Room List", "Eve", "!rooms"),
    ]:
        processor.process_message(room, user, message)


if __name__ == "__main__":
    main()
