#!/usr/bin/env python3
"""Debug script to see what windows match the current pattern"""

import re
from pywinauto import Application

def debug_windows():
    """Show all windows matching various title patterns"""
    
    # Try different patterns that might work
    patterns = [
        r"(?i).*Players__Lounge.*Video Chat Room.*",
        r"(?i).*Players Lounge.*Video Chat Room.*",
        r"(?i).*camfrog.*",
        r"(?i).*Players.*Lounge.*",
        r".*"
    ]
    
    print("Trying different patterns to find Camfrog windows...")
    
    for i, pattern in enumerate(patterns):
        print(f"\nPattern {i+1}: {pattern}")
        try:
            app = Application(backend="uia").connect(title_re=pattern)
            candidates = app.windows()
            
            if len(candidates) > 0:
                print(f"  Found {len(candidates)} windows:")
                for j, window in enumerate(candidates):
                    try:
                        title = window.window_text()
                        rect = window.rectangle()
                        class_name = window.class_name()
                        
                        print(f"    Window {j+1}: '{title}' (class: {class_name})")
                        print(f"      Size: {rect.width()} x {rect.height()}")
                    except Exception as e:
                        print(f"      Error getting info: {e}")
            else:
                print("  No windows found")
                
        except Exception as e:
            # print(f"  Error with this pattern: {type(e).__name__}: {e}")
            pass

if __name__ == "__main__":
    debug_windows()