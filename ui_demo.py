"""
UI Automation Demo Script
Demonstrates how to use the new UI automation module with Camfrog
"""

from ui_automation import CamfrogUIAutomation

def main():
    """Main demo function"""
    print("Camfrog UI Automation Demo")
    print("=" * 30)
    
    # Create UI automation instance
    ui_automation = CamfrogUIAutomation()
    
    print("\n1. Testing connection to Camfrog...")
    
    # Try to connect (this will only work if Camfrog is running)
    if ui_automation.connect_to_camfrog():
        print("✓ Successfully connected to Camfrog")
        
        print("\n2. Extracting user list...")
        usernames = ui_automation.get_user_list()
        
        if usernames:
            print(f"✓ Found {len(usernames)} users:")
            for i, username in enumerate(usernames, 1):
                print(f"   {i}. {username}")
        else:
            print("⚠ No users found or unable to extract user list")
            
        print("\n3. Getting user count...")
        user_count = ui_automation.get_user_count()
        print(f"✓ User count: {user_count}")
        
    else:
        print("⚠ Could not connect to Camfrog")
        print("Note: Make sure Camfrog is running before trying to connect")
    
    print("\nDemo completed.")

if __name__ == "__main__":
    main()