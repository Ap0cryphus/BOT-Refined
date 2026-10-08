#!/usr/bin/env python3
"""
Test script for the position-based tab detection functionality.
"""

import sys
import os

# Add the project root to the path so we can import modules
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from ui_automation import CamfrogUIAutomation
from config import ROOM_TAB_POSITIONS

def test_position_detection():
    """Test that position detection works correctly."""
    print("Testing position-based tab detection...")
    
    # Test each room position
    test_cases = [
        (1390, 50, "Room List"),
        (1550, 50, "Players__Lounge"), 
        (1710, 50, "Drama_Central")
    ]
    
    bot = CamfrogUIAutomation()
    
    for x, y, expected_room in test_cases:
        result = bot.find_room_by_position(x, y)
        if result == expected_room:
            print(f"✓ Position ({x}, {y}) correctly identified as '{result}'")
        else:
            print(f"✗ Position ({x}, {y}) expected '{expected_room}' but got '{result}'")

def test_get_current_room():
    """Test that get_current_room function works."""
    print("\nTesting get_current_room function...")
    
    bot = CamfrogUIAutomation()
    
    # This should work without error
    try:
        room = bot.get_current_room()
        print(f"get_current_room() returned: {room}")
        print("✓ get_current_room() executed successfully")
    except Exception as e:
        print(f"✗ get_current_room() failed with error: {e}")

if __name__ == "__main__":
    test_position_detection()
    test_get_current_room()
    print("\nPosition detection tests completed.")