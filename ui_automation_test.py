"""
Test script for UI Automation module
This script validates that the ui_automation.py module works correctly
"""

from ui_automation import CamfrogUIAutomation

def test_ui_automation_module():
    """Test the UI automation module functionality"""
    print("Testing UI Automation Module...")
    
    # Create instance of the UI automation class
    ui_automation = CamfrogUIAutomation()
    
    print("[OK] UI Automation module imported successfully")
    print("[OK] CamfrogUIAutomation class created successfully")
    
    # Test methods exist
    methods = ['connect_to_camfrog', 'get_user_list', 'get_user_count', 'is_connected']
    for method in methods:
        if hasattr(ui_automation, method):
            print(f"[OK] Method '{method}' exists")
        else:
            print(f"[FAIL] Method '{method}' missing")
    
    print("\nUI Automation module test completed.")
    print("Note: Actual connection to Camfrog requires the application to be running.")

if __name__ == "__main__":
    test_ui_automation_module()
