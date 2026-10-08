#!/usr/bin/env python3
"""Set up the dependencies and folders for the UI-Automation build.

No OCR, screen-capture, DXCam, OpenCV, Pillow, or Tesseract package is
installed by this script. Those are deliberately deferred to a later release.
"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path


def check_python_version() -> bool:
    version = sys.version_info
    if version >= (3, 10):
        print(f"Python {version.major}.{version.minor}.{version.micro}: OK")
        return True
    print("Python 3.10 or newer is required.")
    return False


def install_packages() -> bool:
    packages = ("pywinauto>=0.6.9", "pywin32>=306", "comtypes>=1.4")
    try:
        subprocess.check_call([sys.executable, "-m", "pip", "install", *packages])
    except subprocess.CalledProcessError as error:
        print(f"Dependency installation failed: {error}")
        return False
    return True


def setup_directories() -> None:
    root = Path(__file__).resolve().parent
    for relative in ("logs", "data", "data/suppressed"):
        path = root / relative
        path.mkdir(parents=True, exist_ok=True)
        print(f"Ready: {path}")


def main() -> int:
    if not check_python_version():
        return 1
    if not install_packages():
        return 1
    setup_directories()
    print("Setup complete. Run: .venv\\Scripts\\python.exe camfrog_boy.py")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
