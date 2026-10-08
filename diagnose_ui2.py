#!/usr/bin/env python3
"""
Improved diagnostic script to examine Camfrog UIA structure and determine 
what would be easier with an older version.
"""

import re
from config import CAMFROG_WINDOW_TITLE_RE

def analyze_window_titles():
    """Analyze what window titles are actually available"""
    
    print("=== Window Title Analysis ===")
    
    # The actual window title from status bar
    actual_title = "Players__Lounge, Topic: Birthday vibes ✨️"
    print(f"Actual window title: '{actual_title}'")
    
    # Test current pattern
    print(f"\nCurrent pattern: {CAMFROG_WINDOW_TITLE_RE}")
    match = re.search(CAMFROG_WINDOW_TITLE_RE, actual_title)
    print(f"Does actual title match current pattern? {'YES' if match else 'NO'}")
    
    # Show what patterns would match the actual title
    print("\n=== What patterns would work with actual title ===")
    
    # Pattern 1: Original - works for "Players__Lounge, Video Chat Room"
    pattern1 = r"(?i).*Players__Lounge([,:].*?)?\s*Video Chat Room.*"
    match1 = re.search(pattern1, actual_title)
    print(f"Original pattern: {'MATCHES' if match1 else 'NO MATCH'}")
    
    # Pattern 2: More flexible - accepts any text after "Players__Lounge"
    pattern2 = r"(?i).*Players__Lounge.*Video Chat Room.*"
    match2 = re.search(pattern2, actual_title)
    print(f"Flexible pattern: {'MATCHES' if match2 else 'NO MATCH'}")
    
    # Pattern 3: Even more flexible - just look for "Players__Lounge"
    pattern3 = r"(?i).*Players__Lounge.*"
    match3 = re.search(pattern3, actual_title)
    print(f"Minimal pattern: {'MATCHES' if match3 else 'NO MATCH'}")
    
    # Show the window title structure
    print("\n=== Window Title Structure Analysis ===")
    print("Actual title components:")
    parts = actual_title.split()
    for i, part in enumerate(parts):
        print(f"  {i}: '{part}'")
    
    # Let's see what the different patterns would match
    print("\n=== Pattern Matching Comparison ===")
    test_cases = [
        "Players__Lounge: Video Chat Room",
        "Players__Lounge, Video Chat Room", 
        "Players__Lounge, Topic: Birthday vibes ✨️",
        "Players__Lounge Video Chat Room",
        "Camfrog Video Chat Room"
    ]
    
    patterns = [
        ("Original pattern", pattern1),
        ("Flexible pattern", pattern2),
        ("Minimal pattern", pattern3)
    ]
    
    for case in test_cases:
        print(f"\nTesting '{case}':")
        for name, pattern in patterns:
            match = re.search(pattern, case)
            status = "✓" if match else "✗"
            print(f"  {status} {name}")
            
def analyze_ui_structure():
    """Analyze UI structure elements that would make older versions easier"""
    
    print("\n\n=== UI Structure Analysis ===")
    print("Key factors that make information extraction easier in older versions:")
    
    factors = [
        "1. Simpler control hierarchy - fewer nested elements",
        "2. More predictable control names and IDs",
        "3. Consistent element locations across different room types",
        "4. Less dynamic UI updates (fewer animations/transitions)",
        "5. Better documented UIA tree structures",
        "6. Fewer custom controls requiring complex parsing",
        "7. More stable accessibility properties",
        "8. Less reliance on CEF rendering complexity"
    ]
    
    for factor in factors:
        print(f"  {factor}")
        
    print("\n=== What the current codebase does well ===")
    current_approach = [
        "Uses only UI Automation (no OCR, screenshots, or template matching)",
        "Relies on accessible controls that expose text directly",
        "Doesn't depend on visual appearance for information extraction",
        "Designed to work with Camfrog's UIA interface"
    ]
    
    for approach in current_approach:
        print(f"  ✓ {approach}")

if __name__ == "__main__":
    analyze_window_titles()
    analyze_ui_structure()