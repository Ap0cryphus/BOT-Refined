"""Integration smoke test for the UI-Automation-only build."""

from pathlib import Path

from camfrog_bot import CamfrogBot
from config import DXCAM_ENABLED, OCR_ENABLED, TESSERACT_ENABLED
from ui_automation import CamfrogUIAutomation


def main() -> int:
    bot = CamfrogBot(dry_run=True)
    assert isinstance(bot.ui_automation, CamfrogUIAutomation)
    assert not OCR_ENABLED and not DXCAM_ENABLED and not TESSERACT_ENABLED
    for path in (Path("data"), Path("logs"), Path("data/suppressed")):
        assert path.exists(), f"Missing runtime directory: {path}"
    print("UIA-only integration smoke test passed.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
