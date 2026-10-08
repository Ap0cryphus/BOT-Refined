#!/usr/bin/env python3
"""
Example script showing how to process information from different rooms
and setup logic/instructions based on the data received.
"""

import sys
import os
import re
from datetime import datetime

# Add the project root to the path so we can import modules
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from ui_automation import CamfrogUIAutomation
from camfrog_bot import CamfrogBot

class RoomDataProcessor:
    """Process data from different rooms and set up logic based on room context."""
    
    def __init__(self):
        self.ui_automation = CamfrogUIAutomation()
        self.room_commands = {
            "Players__Lounge": [
                # Commands specific to Players__Lounge
                r"!players", 
                r"!lounge",
                r"!room info"
            ],
            "Drama_Central": [
                # Commands specific to Drama_Central  
                r"!drama",
                r"!central",
                r"!showtime"
            ],
            "Room List": [
                # Commands for general room navigation
                r"!rooms",
                r"!list",
                r"!switch"
            ]
        }
        
        self.room_triggers = {
            "Players__Lounge": {
                "trigger_words": ["game", "play", "match"],
                "response_template": "@{user} Let's play some games in the lounge!",
                "action": "send_to_room"
            },
            "Drama_Central": {
                "trigger_words": ["drama", "argument", "fight"],
                "response_template": "@{user} This is a drama central - keep it civil!",
                "action": "send_to_room"
            }
        }
        
    def process_message(self, room_name, user, message):
        """Process a message based on which room it came from."""
        print(f"[{room_name}] {user}: {message}")
        
        # Check if message contains any commands
        message_lower = message.lower()
        
        # General command handling
        if message_lower.startswith("!"):
            self.handle_command(room_name, user, message)
            
        # Room-specific triggers
        if room_name in self.room_triggers:
            trigger_config = self.room_triggers[room_name]
            for trigger_word in trigger_config["trigger_words"]:
                if trigger_word in message_lower:
                    response = trigger_config["response_template"].format(user=user)
                    print(f"  -> Triggered: {response}")
                    # In a real implementation, we would send this response
                    return response
                    
        return None
    
    def handle_command(self, room_name, user, message):
        """Handle commands based on room context."""
        print(f"  Command detected in {room_name}: {message}")
        
        # Check for room-specific commands
        if room_name == "Players__Lounge":
            if "!players" in message.lower():
                print("  -> Players__Lounge command: Displaying player info")
            elif "!lounge" in message.lower():
                print("  -> Lounge command: Showing lounge activities")
                
        elif room_name == "Drama_Central":
            if "!drama" in message.lower():
                print("  -> Drama_Central command: Displaying drama topics")
            elif "!central" in message.lower():
                print("  -> Central command: Showing central discussions")
                
        elif room_name == "Room List":
            if "!rooms" in message.lower():
                print("  -> Room list command: Showing available rooms")
    
    def get_room_context(self, room_name):
        """Get context information for a specific room."""
        context = {
            "room": room_name,
            "timestamp": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            "active_users": self.ui_automation.get_user_list(),
            "message_count": len(self.ui_automation.get_chat_events())
        }
        return context

def main():
    """Main function to demonstrate room data processing."""
    print("Camfrog Room Data Processor")
    print("=" * 40)
    
    processor = RoomDataProcessor()
    
    # Example of simulated room messages
    example_messages = [
        ("Players__Lounge", "Alice", "!players"),
        ("Players__Lounge", "Bob", "Let's play a game!"), 
        ("Drama_Central", "Charlie", "This is getting heated"),
        ("Drama_Central", "David", "!drama"),
        ("Room List", "Eve", "!rooms")
    ]
    
    print("Processing example messages from different rooms:")
    print("-" * 40)
    
    for room, user, message in example_messages:
        processor.process_message(room, user, message)
        context = processor.get_room_context(room)
        print(f"  Context: {context}")
        print()
        
    print("Data processing demonstration completed.")

if __name__ == "__main__":
    main()