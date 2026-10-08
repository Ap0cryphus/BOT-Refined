#!/usr/bin/env python3
"""
Enhanced diagnostic script to prepare for multi-room support in Camfrog.
This will help us understand how to extract information from tabbed chatrooms.
"""

import re
from pywinauto import Desktop

def analyze_tabbed_structure():
    """Analyze the tabbed structure of Camfrog rooms"""
    
    print("=== Tabbed Room Structure Analysis ===")
    
    # The three room titles you mentioned:
    room_titles = [
        "Room List",           # Not needed but may help with control identification
        "Players__Lounge",     # Main chatroom we'll work with most
        "Drama_Central"        # Secondary chatroom
    ]
    
    print("Tabbed room titles from left to right:")
    for i, title in enumerate(room_titles, 1):
        print(f"  {i}. '{title}'")
        
    # Pattern matching analysis
    print("\n=== Pattern Matching Analysis ===")
    
    # Current pattern from config.py (this might need updating)
    current_pattern = r"(?i).*Players__Lounge([,:].*?)?\s*Video Chat Room.*"
    print(f"Current pattern: {current_pattern}")
    
    # Test against all room titles
    for title in room_titles:
        match = re.search(current_pattern, title)
        print(f"'{title}': {'MATCHES' if match else 'NO MATCH'}")
        
    # What patterns would work better?
    print("\n=== Suggested Flexible Patterns ===")
    
    flexible_patterns = [
        r"(?i).*Players__Lounge.*",  # Most flexible - matches any variation
        r"(?i).*Lounge.*",           # Even more flexible
        r"(?i).*([A-Za-z_]+).*"      # Matches any room name with underscores
    ]
    
    for i, pattern in enumerate(flexible_patterns, 1):
        print(f"  {i}. Pattern: {pattern}")
        for title in room_titles:
            match = re.search(pattern, title)
            print(f"     '{title}': {'MATCHES' if match else 'NO MATCH'}")

def analyze_room_container():
    """Analyze how rooms are structured within the main container"""
    
    print("\n\n=== Room Container Analysis ===")
    
    try:
        desktop = Desktop(backend="uia")
        windows = desktop.windows()
        
        # Look for the main Camfrog window that contains all rooms
        main_camfrog_window = None
        for window in windows:
            title = window.window_text()
            if title and ('camfrog' in title.lower() or 'Players__Lounge' in title or 'Drama_Central' in title):
                print(f"Found potential Camfrog window: '{title}'")
                # Check if it's the main container by looking at control structure
                try:
                    descendants = window.descendants()
                    print(f"  Has {len(descendants)} descendant controls")
                    
                    # Look for tab-related controls
                    tabs = [d for d in descendants if 'tab' in (d.element_info.control_type or '').lower()]
                    print(f"  Found {len(tabs)} tab controls")
                    
                    # Look for room-specific controls
                    room_controls = [d for d in descendants if 'room' in (d.window_text() or '').lower()]
                    print(f"  Found {len(room_controls)} room-related controls")
                    
                except Exception as e:
                    print(f"  Error analyzing window structure: {e}")
                    
    except Exception as e:
        print(f"Error accessing windows: {e}")

def design_multi_room_approach():
    """Design approach for handling multiple rooms"""
    
    print("\n\n=== Multi-Room Support Design ===")
    
    print("To support multiple rooms, we need:")
    
    approaches = [
        "1. Dynamic window title detection based on room content",
        "2. Tab navigation capability within the main container",
        "3. Room-specific control identification patterns",
        "4. State management for switching between rooms",
        "5. Robust error handling when rooms are not available"
    ]
    
    for approach in approaches:
        print(f"  ✓ {approach}")
        
    print("\nKey Implementation Elements:")
    
    elements = [
        "• Use more flexible title patterns that work with all room types",
        "• Implement tab control identification and switching",
        "• Create room-specific parsing logic for different room structures",
        "• Add room state tracking (current room, room availability)",
        "• Implement retry mechanisms for room connections"
    ]
    
    for element in elements:
        print(f"  • {element}")

def evaluate_current_codebase():
    """Evaluate how the current codebase needs to be enhanced"""
    
    print("\n\n=== Current Codebase Enhancement Needs ===")
    
    # The main areas that need enhancement
    enhancements = {
        "Title Pattern Flexibility": "Update the pattern to work with all room types",
        "Tab Navigation Support": "Add ability to identify and switch between tabs",
        "Room State Management": "Track which room is currently active",
        "Multi-Window Handling": "Support multiple Camfrog windows/rooms simultaneously",
        "Error Recovery": "Better handling when rooms become unavailable"
    }
    
    for area, description in enhancements.items():
        print(f"• {area}: {description}")
        
    # Suggested improvements to config.py
    print("\n=== Suggested Config Improvements ===")
    print("In config.py, consider updating:")
    print("CAMFROG_WINDOW_TITLE_RE = r'(?i).*Players__Lounge.*Video Chat Room.*|(?i).*Drama_Central.*Video Chat Room.*|(?i).*Room List.*'")
    print("Or even more flexible:")
    print("CAMFROG_WINDOW_TITLE_RE = r'(?i).*([A-Za-z_]+).*Video Chat Room.*'")

if __name__ == "__main__":
    analyze_tabbed_structure()
    analyze_room_container()
    design_multi_room_approach()
    evaluate_current_codebase()