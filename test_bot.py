"""Offline tests for the UIA bot; no Camfrog window is required."""

from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from camfrog_bot import CamfrogBot, CamfrogStore, detect_moderation
from config import (
    ACTIVE_SPEAKER_RECT,
    BOT_USERNAME,
    CHAT_INPUT_RECT,
    CHAT_WINDOW_RECT,
    MIC_CONFIRM_PERSIST_SECONDS,
    TALK_BUTTON_RECT,
    USER_LIST_RECT,
)
from ui_automation import (
    CamfrogUIAutomation,
    UIANode,
    clean_username,
    extract_users_header_count,
    is_user_list_header,
)


class FakeAutomation:
    def __init__(self) -> None:
        self.events: list[dict[str, str]] = []
        self.sent: list[str] = []
        self.tts_broadcasts: list[str] = []
        self.user_list: list[str] = ["Stonerwayne1000", "Rosie", "nico1ee"]
        self.active_speaker: str | None = None
        self.last_error = ""

    def connect_to_camfrog(self) -> bool:
        return True

    def get_user_list(self) -> list[str]:
        return list(self.user_list)

    def get_chat_events(self) -> list[dict[str, str]]:
        return list(self.events)

    def get_active_speaker(self) -> str | None:
        return self.active_speaker

    def send_chat_message(self, message: str) -> bool:
        self.sent.append(message)
        return True

    def broadcast_tts_via_vbcable(self, text: str, dry_run: bool = False) -> bool:
        self.tts_broadcasts.append(text)
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

    def test_ui_text_and_viewing_lurkers_filtered(self) -> None:
        self.assertEqual(clean_username("8:13 AM"), "")
        self.assertEqual(clean_username("GIFTUsers2"), "")
        self.assertEqual(clean_username("YOU ARE VIEWING 3", (2359, 141, 2559, 163)), "")
        self.assertEqual(clean_username("VIEWING 5", (2359, 185, 2559, 207)), "")
        self.assertEqual(clean_username("LURKERS 14", (2359, 520, 2559, 542)), "")
        self.assertEqual(clean_username("USERS (48)", (2359, 165, 2543, 187)), "")
        self.assertEqual(extract_users_header_count("USERS (48)"), 48)
        self.assertEqual(extract_users_header_count("USERS 35"), 35)
        self.assertEqual(extract_users_header_count("MEMBERS 17"), 17)
        self.assertIsNone(extract_users_header_count("YOU ARE VIEWING (0)"))
        self.assertIsNone(extract_users_header_count("VIEWING 4"))
        self.assertIsNone(extract_users_header_count("LURKERS (12)"))
        self.assertTrue(is_user_list_header("YOU ARE VIEWING 2"))
        self.assertTrue(is_user_list_header("LURKERS 19"))
        self.assertTrue(is_user_list_header("USERS (48)"))
        self.assertEqual(clean_username("HeaderItem", (2303, 141, 2559, 163)), "")
        self.assertEqual(clean_username("Alice_1", (2359, 240, 2543, 262)), "Alice_1")

    def test_active_speaker_detected_even_when_uia_name_empty(self) -> None:
        # Even if Button(50000) at [1506,1174,1548,1190] has empty UIA Name, _find_active_speaker_node detects it
        unnamed_mic_btn = UIANode("Button", "", "CButtonTS", 1506, 1174, 1548, 1190)
        found = CamfrogUIAutomation._find_active_speaker_node([unnamed_mic_btn])
        self.assertIsNotNone(found)
        self.assertEqual(found.rect_tuple, (1506, 1174, 1548, 1190))

    def test_initial_user_list_and_join_quit_duration(self) -> None:
        # Initial users from User List [l=2359,t=141,r=2559,b=1160] are seeded on initialize()
        profile = self.bot.store.user_profile("Stonerwayne1000")
        self.assertIsNotNone(profile)
        self.assertEqual(profile["active"], 1)
        # Simulate Quit: event in Chat Window [l=1281,t=170,r=2355,b=1160]
        self.ui.events = [{"kind": "presence", "action": "quit", "user": "Stonerwayne1000", "text": "", "timestamp": ""}]
        self.bot.poll_once()
        updated = self.bot.store.user_profile("Stonerwayne1000")
        self.assertEqual(updated["active"], 0)

    def test_say_waits_when_mic_occupied_and_broadcasts_when_free(self) -> None:
        # When mic is free ([1506,1174,1548,1190] is empty), !say broadcasts immediately
        self.ui.active_speaker = None
        self.bot._handle_message("Alice_1", "!say Hello Players Lounge", "1:03 PM")
        self.assertEqual(self.ui.tts_broadcasts, ["Hello Players Lounge"])

        # When another user is on the mic at [1506,1174,1548,1190], !say queues until mic clears
        self.ui.active_speaker = "Rosie"
        self.bot._handle_message("Alice_1", "!say Queued until Rosie finishes", "1:04 PM")
        self.assertEqual(len(self.ui.tts_broadcasts), 1)
        # Now Rosie finishes and [1506,1174,1548,1190] erases/clears
        self.ui.active_speaker = None
        self.bot.poll_once()
        self.assertEqual(self.ui.tts_broadcasts, ["Hello Players Lounge", "Queued until Rosie finishes"])

    def test_compound_dataitem_presence_and_user_count_minus_3(self) -> None:
        # 1. Compound DataItem(50029) at [l=1332,r=2330] containing multiple Quit:/Join: events in a single item
        tokens = [
            ("DataItem", "Quit: phoenixrising Quit: liketosquirt Join: ward1dp"),
            ("Text", "Quit:"),
            ("Text", "phoenixrising"),
            ("Text", "Quit:"),
            ("Text", "liketosquirt"),
            ("Text", "Join:"),
            ("Text", "ward1dp"),
        ]
        events = CamfrogUIAutomation._parse_text_tokens_into_events(tokens)
        presence_pairs = [(e["action"], e["user"]) for e in events if e["kind"] == "presence"]
        self.assertIn(("quit", "phoenixrising"), presence_pairs)
        self.assertIn(("quit", "liketosquirt"), presence_pairs)
        self.assertIn(("join", "ward1dp"), presence_pairs)

        # 2. User List counting: sums the 3 ignored section headers (YOU ARE VIEWING # + MEMBERS # + LURKERS #)
        #    and excludes Page scrollbar and OCR header fragments
        ui = CamfrogUIAutomation()
        fake_nodes = [
            UIANode("ListItem", "YOU ARE VIEWING (2)", "", 2359, 141, 2543, 163),
            UIANode("ListItem", "MEMBERS (16)", "", 2359, 165, 2543, 187),
            UIANode("ListItem", "10 Mr,Bl3sS", "", 2359, 190, 2543, 212),
            UIANode("ListItem", "tsyko", "", 2359, 215, 2543, 237),
            UIANode("ListItem", "Gothic_Chaos", "", 2359, 240, 2543, 262),
            UIANode("ListItem", "LURKERS (12)", "", 2359, 520, 2543, 542),
            UIANode("ListItem", "KaeKae_Toad", "", 2359, 545, 2543, 567),
            UIANode("Button", "Page", "", 2544, 200, 2559, 800),
        ]
        count, users = ui._scan_users_header_and_list_from_uia(fake_nodes)
        self.assertEqual(count, 30)  # 2 YOU ARE VIEWING + 16 MEMBERS + 12 LURKERS = 30
        self.assertNotIn("Page", users)
        self.assertIn("tsyko", users)
        self.assertIn("Gothic_Chaos", users)
        self.assertIn("KaeKae_Toad", users)

        # 3. Verify URLs ('https://...') and OCR header fragments ('BERS', 'ERS', 'lol', 'right') are rejected as usernames
        self.assertEqual(clean_username("BERS"), "")
        self.assertEqual(clean_username("ERS"), "")
        self.assertEqual(clean_username("lol"), "")
        self.assertEqual(clean_username("right"), "")
        self.assertEqual(clean_username("https"), "")
        url_events = CamfrogUIAutomation._parse_text_tokens_into_events([
            ("Text", "https://static.camfrogcdn.com/vue_static/pages/room_browser.html#/home"),
            ("Text", "$htickie"),
            ("Text", ":"),
            ("Text", "!triggers"),
        ])
        self.assertEqual(len(url_events), 1)
        self.assertEqual(url_events[0]["user"], "$htickie")
        self.assertEqual(url_events[0]["text"], "!triggers")

        # 4. Verify !triggers dispatches reply to Chat Txt Field
        self.bot._handle_message("$htickie", "!triggers", "2:00 PM")
        self.assertTrue(any("Triggers: !chat" in msg for msg in self.ui.sent))

    def test_calibrated_coordinates_constants(self) -> None:
        self.assertEqual(CHAT_WINDOW_RECT, (1281, 170, 2355, 1160))
        self.assertEqual(CHAT_INPUT_RECT, (1396, 1206, 2497, 1241))
        self.assertEqual(USER_LIST_RECT, (2359, 141, 2559, 1160))
        self.assertEqual(TALK_BUTTON_RECT, (1291, 1169, 1361, 1195))
        self.assertEqual(ACTIVE_SPEAKER_RECT, (1506, 1174, 1548, 1190))
        self.assertEqual(BOT_USERNAME, "KaeKae_Toad")
        self.assertEqual(MIC_CONFIRM_PERSIST_SECONDS, 1.3)


if __name__ == "__main__":
    unittest.main(verbosity=2)
