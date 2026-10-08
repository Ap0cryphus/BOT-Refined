#!/usr/bin/env python3
"""
Comprehensive diagnostic script for Camfrog UIA detection.
This will help identify why the UI automation can't find the running Camfrog window.
"""

import re
import time
from pywinauto import Desktop
from pywinauto.findwindows import WindowNotFoundError

def get_all_windows():
    """Get all windows and their properties"""
    print("=== Getting All Windows ===")
    
    try:
        desktop = Desktop(backend="uia")
        windows = desktop.windows()
        
        print(f"Found {len(windows)} windows total:")
        
        for i, window in enumerate(windows):
            try:
                title = window.window_text()
                rect = window.rectangle()
                control_type = "Unknown"
                
                # Try to get more info about the window
                try:
                    control_type = window.element_info.control_type or "Unknown"
                except:
                    pass
                    
                print(f"  {i+1}. Title: '{title}'")
                print(f"      Type: {control_type}")
                print(f"      Size: {rect.width()} x {rect.height()}")
                print(f"      Visible: {window.is_visible()}")
                print()
                
            except Exception as e:
                print(f"  {i+1}. Error getting window info: {e}")
                
    except Exception as e:
        print(f"Error accessing desktop: {e}")

def check_camfrog_processes():
    """Check for running Camfrog processes"""
    print("=== Checking for Camfrog Processes ===")
    
    import subprocess
    
    try:
        # Check running processes
        result = subprocess.run(['tasklist', '/FI', 'IMAGENAME eq camfrog*.exe'], 
                               capture_output=True, text=True, shell=True)
        print(result.stdout)
        
        # Also check with more general search
        result2 = subprocess.run(['tasklist', '|', 'findstr', 'camfrog'], 
                                capture_output=True, text=True, shell=True)
        if result2.stdout:
            print("\nAdditional Camfrog processes:")
            print(result2.stdout)
            
    except Exception as e:
        print(f"Error checking processes: {e}")

def detailed_pattern_matching():
    """Test various patterns against actual window titles"""
    print("=== Detailed Pattern Matching ===")
    
    # Let's manually test the exact title you mentioned
    actual_title = "Players__Lounge, Topic: Birthday vibes ✨️"
    print(f"Actual window title: '{actual_title}'")
    
    # Current pattern from config.py
    current_pattern = r"(?i).*Players__Lounge([,:].*?)?\s*Video Chat Room.*"
    print(f"\nCurrent pattern: {current_pattern}")
    
    # Test if it matches
    match = re.search(current_pattern, actual_title)
    print(f"Matches current pattern: {'YES' if match else 'NO'}")
    
    # Try some variations that might work better
    patterns_to_try = [
        r"(?i).*Players__Lounge.*Video Chat Room.*",
        r"(?i).*Players__Lounge.*",
        r"(?i).*Lounge.*Chat.*Room.*",
        r"(?i).*Players__Lounge.*Topic.*"
    ]
    
    print("\nTesting alternative patterns:")
    for i, pattern in enumerate(patterns_to_try, 1):
        match = re.search(pattern, actual_title)
        print(f"  {i}. Pattern: {pattern}")
        print(f"     Matches: {'YES' if match else 'NO'}")
        
def test_manual_connection():
    """Try to manually connect to windows using different approaches"""
    print("\n=== Manual Connection Test ===")
    
    from pywinauto import Application
    
    try:
        # Try connecting with different parameters
        print("1. Trying direct connection...")
        app = Application(backend="uia").connect(title_re=r".*Players__Lounge.*")
        windows = app.windows()
        print(f"   Found {len(windows)} windows matching pattern")
        
        for i, win in enumerate(windows):
            try:
                title = win.window_text()
                print(f"   Window {i+1}: '{title}'")
            except Exception as e:
                print(f"   Window {i+1}: Error getting title - {e}")
                
    except Exception as e:
        print(f"Direct connection failed: {e}")
        
    try:
        # Try to find any Camfrog-related windows
        print("\n2. Trying to find any window with 'camfrog' in title...")
        app = Application(backend="uia").connect(title_re=r".*camfrog.*")
        windows = app.windows()
        print(f"   Found {len(windows)} camfrog windows")
        
    except Exception as e:
        print(f"Camfrog connection failed: {e}")

def examine_config():
    """Examine the configuration file"""
    print("\n=== Examining Configuration ===")
    
    try:
        from config import CAMFROG_WINDOW_TITLE_RE
        print(f"Current title pattern from config: {CAMFROG_WINDOW_TITLE_RE}")
        
        # Test it against a few examples
        test_cases = [
            "Players__Lounge: Video Chat Room",
            "Players__Lounge, Video Chat Room", 
            "Players__Lounge, Topic: Birthday vibes ✨️",
            "Camfrog Video Chat Room"
        ]
        
        for case in test_cases:
            match = re.search(CAMFROG_WINDOW_TITLE_RE, case)
            print(f"'{case}': {'MATCHES' if match else 'NO MATCH'}")
            
    except Exception as e:
        print(f"Error reading config: {e}")

if __name__ == "__main__":
    get_all_windows()
    check_camfrog_processes()
    detailed_pattern_matching()
    test_manual_connection()
    examine_config()