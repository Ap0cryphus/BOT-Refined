#!/usr/bin/env python3
"""Debug connection to Camfrog UI"""

import sys
sys.path.insert(0, '.')

from config import CAMFROG_WINDOW_TITLE_RE
from ui_automation import CamfrogUIAutomation

def main():
    print("Testing Camfrog connection...")
    print(f"Title pattern: {repr(CAMFROG_WINDOW_TITLE_RE)}")
    
    # Try direct connection with the title pattern
    try:
        from pywinauto import Application
        app = Application(backend="uia").connect(title_re=CAMFROG_WINDOW_TITLE_RE)
        print("Successfully connected!")
        candidates = app.windows()
        print(f"Found {len(candidates)} windows")
        
        for i, window in enumerate(candidates):
            title = window.window_text()
            print(f"Window {i}: '{title}'")
            
    except Exception as e:
        print(f"Connection failed: {e}")
        
    # Test our class
    print("\nTesting CamfrogUIAutomation class:")
    c = CamfrogUIAutomation()
    result = c.connect_to_camfrog()
    print(f"connect_to_camfrog() returned: {result}")
    print(f"Last error: {c.last_error}")

if __name__ == "__main__":
    main()