from pywinauto import Desktop

windows = Desktop(backend="uia").windows()

for w in windows:
    try:
        print(w.window_text())
    except:
        pass

input("Press Enter to exit...")