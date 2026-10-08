"""Offline verification that the UIA adapter and disabled capture flags load."""

from config import DXCAM_ENABLED, OCR_ENABLED, TESSERACT_ENABLED
from ui_automation import CamfrogUIAutomation


def main() -> int:
    adapter = CamfrogUIAutomation()
    assert not OCR_ENABLED and not DXCAM_ENABLED and not TESSERACT_ENABLED
    print("UI Automation adapter ready.")
    print("OCR, DXCam, and Tesseract are disabled.")
    print(f"Live connection available: {adapter.connect_to_camfrog()}")
    if adapter.last_error:
        print(adapter.last_error)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
