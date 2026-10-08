#!/usr/bin/env python3
"""
Test script to examine UIA structure when Camfrog is running.
This will help determine if older versions would be easier for information extraction.
"""

import sys
import time
from pywinauto import Desktop
from pywinauto.findwindows import WindowNotFoundError

def test_ui_structure():
    """Test what UI elements are available in Camfrog windows"""
    
    print("=== Examining Available Windows ===")
    
    try:
        desktop = Desktop(backend="uia")
        windows = desktop.windows()
        
        print(f"Found {len(windows)} windows:")
        camfrog_windows = []
        
        for i, window in enumerate(windows):
            title = window.window_text()
            if title:
                print(f"  {i+1}. '{title}'")
                # Check if this looks like a Camfrog window
                if 'camfrog' in title.lower() or 'Players__Lounge' in title:
                    camfrog_windows.append((i, window, title))
        
        if not camfrog_windows:
            print("No Camfrog windows found - make sure Camfrog room is open!")
            return
            
        # Try to examine the first Camfrog window
        for i, window, title in camfrog_windows:
            print(f"\n=== Examining Camfrog Window: '{title}' ===")
            try:
                # Get basic window info
                rect = window.rectangle()
                print(f"Window size: {rect.width()} x {rect.height()}")
                
                # Try to get descendants
                descendants = window.descendants()
                print(f"Found {len(descendants)} descendant controls")
                
                # Show first few controls with their properties
                for j, desc in enumerate(descendants[:10]):  # Limit to first 10
                    try:
                        name = desc.window_text() or desc.element_info.name or ""
                        control_type = desc.element_info.control_type or "Unknown"
                        print(f"  {j+1}. Type: {control_type}, Name: '{name}'")
                    except Exception as e:
                        print(f"  {j+1}. Error getting info: {e}")
                
                # Look for specific chat-related controls
                chat_controls = [d for d in descendants if 'chat' in (d.element_info.control_type or '').lower() or 
                                'message' in (d.window_text() or '').lower()]
                print(f"\nFound {len(chat_controls)} potential chat controls")
                
            except Exception as e:
                print(f"Error examining window: {e}")
                
    except Exception as e:
        print(f"Error accessing desktop: {e}")

def test_current_automation():
    """Test the current automation approach"""
    print("\n=== Testing Current Automation Approach ===")
    
    try:
        # Import our automation class
        from ui_automation import CamfrogUIAutomation
        from config import CAMFROG_WINDOW_TITLE_RE
        
        ui = CamfrogUIAutomation()
        
        # Try to connect and see what happens
        print("Attempting connection...")
        success = ui.connect_to_camfrog()
        print(f"Connection successful: {success}")
        
        if not success:
            print(f"Error: {ui.last_error}")
            
        # Print the title pattern being used
        print(f"Using title pattern: {CAMFROG_WINDOW_TITLE_RE}")
        
    except Exception as e:
        print(f"Error in automation test: {e}")

if __name__ == "__main__":
    test_ui_structure()
    test_current_automation()