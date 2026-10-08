"""Offline tests for the UIA-only bot; no Camfrog window is required."""

from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from camfrog_bot import CamfrogBot, CamfrogStore, detect_moderation
from ui_automation import clean_username


class FakeAutomation:
    def __init__(self) -> None:
        self.events: list[dict[str, str]] = []
        self.sent: list[str] = []
        self.last_error = ""

    def connect_to_camfrog(self) -> bool:
        return True

    def get_chat_events(self) -> list[dict[str, str]]:
        return list(self.events)

    def send_chat_message(self, message: str) -> bool:
        self.sent.append(message)
        return True


class CamfrogBotTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp = tempfile.TemporaryDirectory()
        root = Path(self.temp.name)
        self.ui = FakeAutomation()
        self.bot = CamfrogBot(
            automation=self.ui,
            store=CamfrogStore(root / "bot.db", root / "suppressed"),
        )
        self.assertTrue(self.bot.initialize())

    def tearDown(self) -> None:
        self.temp.cleanup()

    def test_records_message_and_serves_info(self) -> None:
        self.ui.events = [{"kind": "message", "user": "Alice_1", "text": "Python Python testing", "timestamp": "1:00 PM"}]
        self.bot.poll_once()
        profile = self.bot.store.user_profile("Alice_1")
        self.assertIsNotNone(profile)
        self.assertEqual(profile["message_count"], 1)
        self.bot._handle_message("Alice_1", "!info on Alice_1", "1:01 PM")
        self.assertTrue(any("Alice_1: 2 messages" in message for message in self.ui.sent))

    def test_suppression_can_be_reversed_by_the_same_user(self) -> None:
        self.bot._handle_message("Alice_1", "A stored line", "1:00 PM")
        self.bot._handle_message("Alice_1", "!suppress", "1:01 PM")
        self.assertTrue(self.bot.store.is_suppressed("Alice_1"))
        self.bot._handle_message("Alice_1", "!unsuppress", "1:02 PM")
        self.assertFalse(self.bot.store.is_suppressed("Alice_1"))
        self.assertIsNotNone(self.bot.store.user_profile("Alice_1"))

    def test_moderation_parser_rejects_prose(self) -> None:
        self.assertEqual(
            detect_moderation("Mod_1 unbanned User_2"),
            {"actor": "Mod_1", "target": "User_2", "action": "unbanned"},
        )
        self.assertIsNone(detect_moderation("Please do not ban User_2"))

    def test_ui_text_is_not_guessed_as_a_username(self) -> None:
        self.assertEqual(clean_username("8:13 AM"), "")
        self.assertEqual(clean_username("GIFTUsers2"), "")
        self.assertEqual(clean_username("Alice_1"), "Alice_1")


if __name__ == "__main__":
    unittest.main(verbosity=2)
