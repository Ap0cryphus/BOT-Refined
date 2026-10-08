#!/usr/bin/env python3
"""
Diagnostic script to examine Camfrog UIA structure and determine 
what would be easier with an older version.
"""

import re
from config import CAMFROG_WINDOW_TITLE_RE
from ui_automation import CamfrogUIAutomation

def diagnose_camlfrog_ui():
    """Diagnose what's available in the current Camfrog setup"""
    
    print("=== Camfrog UIA Diagnosis ===")
    
    # Show the expected pattern
    print(f"Expected title pattern: {CAMFROG_WINDOW_TITLE_RE}")
    
    # Test the actual pattern against known titles
    test_titles = [
        "Players__Lounge, Topic: Birthday vibes ✨️",
        "Players__Lounge: Video Chat Room", 
        "Players__Lounge, Video Chat Room",
        "Camfrog Video Chat Room",
        "Video Chat Room Players__Lounge"
    ]
    
    print("\n=== Pattern Matching Results ===")
    for title in test_titles:
        match = re.search(CAMFROG_WINDOW_TITLE_RE, title)
        print(f"'{title}': {'MATCHES' if match else 'NO MATCH'}")
    
    # Try to connect with debug info
    print("\n=== Attempting Connection ===")
    ui_automation = CamfrogUIAutomation()
    
    try:
        # First let's see what windows are actually available
        from pywinauto import Desktop
        desktop = Desktop(backend="uia")
        windows = desktop.windows()
        
        print(f"Found {len(windows)} windows:")
        for i, window in enumerate(windows):
            title = window.window_text()
            if title:
                print(f"  {i+1}. '{title}'")
                # Check if it matches our pattern
                match = re.search(CAMFROG_WINDOW_TITLE_RE, title)
                if match:
                    print(f"     -> MATCHES expected pattern!")
                    
    except Exception as e:
        print(f"Error getting window list: {e}")
        
    # Try to connect with the actual UIA class
    print("\n=== Testing UIA Connection ===")
    success = ui_automation.connect_to_camfrog()
    print(f"Connection result: {success}")
    if ui_automation.last_error:
        print(f"Last error: {ui_automation.last_error}")

if __name__ == "__main__":
    diagnose_camlfrog_ui()