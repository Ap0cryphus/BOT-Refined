import os
import sys
import time
import ctypes
from ctypes import wintypes
import pyperclip
import pyautogui
import win32gui
import win32con
import win32process
from pywinauto import Desktop

def test_cef_accessibility():
    print("=" * 65)
    print(" TESTING CEF / CHROMIUM CHAT WINDOW CAPTURE")
    print("=" * 65)

    # Find the Camfrog Room Window with CefBrowser
    target_hwnds = []
    def enum_cb(hwnd, extra):
        if win32gui.IsWindowVisible(hwnd):
            title = win32gui.GetWindowText(hwnd)
            cls = win32gui.GetClassName(hwnd)
            if "camfrog" in title.lower() or cls == "#32770":
                # Check if it has a CefBrowser or Chrome child
                cef_found = []
                def enum_child(ch_hwnd, _):
                    ch_cls = win32gui.GetClassName(ch_hwnd)
                    if "cef" in ch_cls.lower() or "chrome" in ch_cls.lower():
                        cef_found.append((ch_hwnd, ch_cls))
                win32gui.EnumChildWindows(hwnd, enum_child, None)
                if cef_found:
                    target_hwnds.append((hwnd, title, cef_found))
    win32gui.EnumWindows(enum_cb, None)

    print(f"Found {len(target_hwnds)} Camfrog window(s) containing CEF/Chromium:")
    for hwnd, title, cefs in target_hwnds:
        print(f"\nWindow HWND: {hwnd} | Title: '{title}'")
        for ch_hwnd, ch_cls in cefs:
            print(f"   -> Sub-window HWND: {ch_hwnd} | Class: '{ch_cls}'")

    # TEST 1: Wake up Chromium Accessibility via WM_GETOBJECT
    print("\n--- [TEST 1] Waking Chromium Accessibility (WM_GETOBJECT) ---")
    OBJID_CLIENT = 0xFFFFFFFC
    for hwnd, title, cefs in target_hwnds:
        for ch_hwnd, ch_cls in cefs:
            if "Chrome_RenderWidgetHostHWND" in ch_cls:
                print(f"Pinging Chrome Legacy Window (HWND {ch_hwnd}) with WM_GETOBJECT...")
                ctypes.windll.user32.SendMessageW(ch_hwnd, 0x003D, 0, OBJID_CLIENT)

    time.sleep(0.5)

    # Now inspect with UIA Desktop
    print("\nQuerying UI Automation tree for text elements inside Camfrog...")
    try:
        app_uia = Desktop(backend="uia")
        for hwnd, title, cefs in target_hwnds:
            try:
                win_elem = app_uia.window(handle=hwnd)
                print(f"\nExamining elements under '{title}'...")
                texts = []
                for elem in win_elem.descendants():
                    try:
                        name = elem.element_info.name
                        ctrl = elem.element_info.control_type
                        if name and len(name.strip()) > 1 and name.strip() not in texts:
                            texts.append(name.strip())
                            if len(texts) <= 25:
                                print(f"   [{ctrl}] {name.strip()[:80]}")
                    except Exception:
                        pass
                print(f"Total unique text nodes found via UIA: {len(texts)}")
            except Exception as e:
                print(f"Error querying window {hwnd}: {e}")
    except Exception as e:
        print(f"UIA Error: {e}")

    # TEST 2: Non-destructive Clipboard Probe
    print("\n--- [TEST 2] Testing Chat Pane Selection / Clipboard Capture ---")
    print("Do you want to test clicking the chat pane and grabbing text via clipboard?")
    print("Press [ENTER] to test, or Ctrl+C to skip...")
    try:
        input()
    except (KeyboardInterrupt, EOFError):
        return

    orig_clip = pyperclip.paste()
    for hwnd, title, cefs in target_hwnds:
        for ch_hwnd, ch_cls in cefs:
            if "Chrome_RenderWidgetHostHWND" in ch_cls:
                rect = win32gui.GetWindowRect(ch_hwnd)
                left, top, right, bottom = rect
                cx = (left + right) // 2
                cy = (top + bottom) // 2
                print(f"Clicking inside CEF window at ({cx}, {cy})...")
                win32gui.SetForegroundWindow(hwnd)
                time.sleep(0.2)
                pyautogui.click(cx, cy)
                time.sleep(0.1)
                pyautogui.hotkey('ctrl', 'a')
                time.sleep(0.1)
                pyautogui.hotkey('ctrl', 'c')
                time.sleep(0.2)
                # Unselect by clicking again or pressing Esc
                pyautogui.press('right')
                
                captured = pyperclip.paste()
                print("\n[CLIPBOARD RESULT]:")
                if captured and captured != orig_clip:
                    lines = captured.splitlines()
                    print(f"✓ SUCCESSFULLY CAPTURED {len(lines)} lines from chat!")
                    print("First 10 lines captured directly from CEF:")
                    for l in lines[:10]:
                        print(f"   | {l}")
                else:
                    print("x Clipboard did not capture text (or matched previous clipboard).")

if __name__ == "__main__":
    test_cef_accessibility()
