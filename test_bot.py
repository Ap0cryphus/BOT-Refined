"""Offline tests for the UIA bot and PepeFrog Cross-Game Automation Framework; no live window is required."""

from __future__ import annotations

import tempfile
import threading
import time
import unittest
import wave
from pathlib import Path

from camfrog_bot import CamfrogBot, CamfrogStore, detect_moderation
from config import (
    ACTIVE_SPEAKER_RECT,
    BOT_USERNAME,
    CHAT_INPUT_RECT,
    CHAT_WINDOW_RECT,
    MIC_CONFIRM_PERSIST_SECONDS,
    MIC_GRAB_FAST_CLICKS,
    MIC_GRAB_FAST_CLICK_DELAY,
    MIC_GRAB_HOLD_MIN_SECONDS,
    MIC_GRAB_MAX_ATTEMPTS,
    TALK_BUTTON_RECT,
    USER_LIST_RECT,
)
from main import PepeFrogOrchestrator, precision_sleep_until
from strategy_core import (
    BEG_COOLDOWN_SECONDS,
    JACKPOT_POOL_CAP_PAT,
    LOTTO_TICKET_COST_PAT,
    SPIN_FLAT_COST_PAT,
    PepeFrogStrategyEngine,
)
from ui_automation import (
    _AUDIO_CAPTURE_LOCK,
    _VIRTUAL_INPUT_KEYWORDS,
    COQUI_CLONE_EMPTY,
    COQUI_CLONE_VOICE,
    COQUI_DEFAULT_VOICE,
    COQUI_FEMALE_VOICES,
    EDGE_FEMALE_VOICES,
    KOKORO_DEFAULT_VOICE,
    KOKORO_FEMALE_VOICES,
    CamfrogUIAutomation,
    CoquiXTTSVoiceEngine,
    LocalKokoroVoiceEngine,
    UIANode,
    clean_username,
    coqui_voice_catalog,
    edge_female_voice_catalog,
    extract_users_header_count,
    is_coqui_voice,
    is_kokoro_voice,
    is_user_list_header,
    kokoro_voice_catalog,
    resolve_compute_device,
)
from uia_interface import UIAInterface
from vision_analyzer import VisionAnalyzer


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
        # Bot boots in SILENT mode: no room replies until the operator flips silent off / sends !chat.
        self.bot._handle_message("Alice_1", "!info on Alice_1", "1:01 PM")
        self.assertEqual(self.ui.sent, [], "Silent boot must suppress all room replies")
        self.bot.silent_switch(False)
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


    def test_physical_input_device_excludes_virtual_and_prefers_real_mic(self):
        ui = CamfrogUIAutomation()

        def fake_query_devices():
            return [
                {'name': 'VB-Cable (Input)', 'index': 1, 'max_input_channels': 2},
                {'name': 'Stereo Mix', 'index': 2, 'max_input_channels': 2},
                {'name': 'USB headset mic', 'index': 3, 'max_input_channels': 1},
                {'name': 'Loopback Audio', 'index': 4, 'max_input_channels': 1},
            ]

        ui._query_devices = fake_query_devices  # type: ignore[attr-defined]
        dev, label = ui._physical_input_device()
        self.assertEqual(dev['name'], 'USB headset mic')
        self.assertEqual(dev['index'], 3)
        self.assertFalse(any(k in label.lower() for k in _VIRTUAL_INPUT_KEYWORDS))

    def test_physical_input_device_requires_positive_input_channels(self):
        ui = CamfrogUIAutomation()

        def fake_query_devices():
            return [
                {'name': 'VB-Cable (Loopback)', 'index': 1, 'max_input_channels': 0},
                {'name': 'What U Hear', 'index': 2, 'max_input_channels': 0},
            ]

        ui._query_devices = fake_query_devices  # type: ignore[attr-defined]
        dev, label = ui._physical_input_device()
        self.assertIsNone(dev)
        self.assertIn('Default Input', label)
        self.assertFalse(ui.sample_capture_active)

    def test_physical_input_device_skips_when_lock_held_by_listen(self):
        ui = CamfrogUIAutomation()
        dev, label = ui._physical_input_device()
        self.assertIsNotNone(dev)
        with _AUDIO_CAPTURE_LOCK:
            dev2, label2 = ui._physical_input_device()
            self.assertIsNotNone(dev2)
        self.assertEqual(label, label2)
        self.assertFalse(ui.sample_capture_active)

    def test_active_speaker_detected_even_when_uia_name_empty(self) -> None:
        unnamed_mic_btn = UIANode("Button", "", "CButtonTS", 1506, 1174, 1548, 1190)
        found = CamfrogUIAutomation._find_active_speaker_node([unnamed_mic_btn])
        self.assertIsNotNone(found)
        self.assertEqual(found.rect_tuple, (1506, 1174, 1548, 1190))

    def test_initial_user_list_and_join_quit_duration(self) -> None:
        profile = self.bot.store.user_profile("Stonerwayne1000")
        self.assertIsNotNone(profile)
        self.assertEqual(profile["active"], 1)
        self.ui.events = [{"kind": "presence", "action": "quit", "user": "Stonerwayne1000", "text": "", "timestamp": ""}]
        self.bot.poll_once()
        updated = self.bot.store.user_profile("Stonerwayne1000")
        self.assertEqual(updated["active"], 0)

    def test_say_waits_when_mic_occupied_and_broadcasts_when_free(self) -> None:
        # Bot boots SILENT: !say broadcasts are suppressed until the operator flips silent off (!chat / !shutup off).
        self.ui.active_speaker = None
        self.bot._handle_message("Alice_1", "!say Hello Players Lounge", "1:03 PM")
        self.assertEqual(self.ui.tts_broadcasts, [], "Silent boot must suppress !say broadcasts")
        self.bot.silent_switch(False)

        self.bot._handle_message("Alice_1", "!say Hello Players Lounge", "1:03 PM")
        self.assertEqual(self.ui.tts_broadcasts, ["Hello Players Lounge"])

        self.ui.active_speaker = "Rosie"
        self.bot._handle_message("Alice_1", "!say Queued until Rosie finishes", "1:04 PM")
        self.assertEqual(len(self.ui.tts_broadcasts), 1)
        self.ui.active_speaker = None
        self.bot.poll_once()
        self.assertEqual(self.ui.tts_broadcasts, ["Hello Players Lounge", "Queued until Rosie finishes"])

    def test_compound_dataitem_presence_and_user_count_minus_3(self) -> None:
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
        self.assertEqual(count, 30)
        self.assertNotIn("Page", users)
        self.assertIn("tsyko", users)
        self.assertIn("Gothic_Chaos", users)
        self.assertIn("KaeKae_Toad", users)

    def test_calibrated_coordinates_constants(self) -> None:
        self.assertEqual(CHAT_WINDOW_RECT, (1281, 170, 2355, 1160))
        self.assertEqual(CHAT_INPUT_RECT, (1396, 1206, 2497, 1241))
        self.assertEqual(USER_LIST_RECT, (2359, 141, 2559, 1160))
        self.assertEqual(TALK_BUTTON_RECT, (1291, 1169, 1361, 1195))
        self.assertEqual(ACTIVE_SPEAKER_RECT, (1506, 1174, 1548, 1190))
        self.assertEqual(BOT_USERNAME, "KaeKae_Toad")
        self.assertEqual(MIC_CONFIRM_PERSIST_SECONDS, 1.3)

    def test_relative_monitor_coordinate_translation(self) -> None:
        ui = CamfrogUIAutomation()
        ui._last_valid_win_rect = (0, 0, 1294, 1399)
        norm = ui._normalize_rect_to_calibrated(233, 1174, 275, 1190)
        self.assertEqual(norm, (1506, 1174, 1548, 1190))
        scr_pt = ui._calibrated_to_screen_point(1946, 1223)
        self.assertEqual(scr_pt, (673, 1223))

    def test_unscrolled_chat_nodes_below_viewport_still_recorded(self) -> None:
        ui = CamfrogUIAutomation()
        ui._nodes = [
            UIANode("Text", "tsyko", "", 1300, 1320, 1360, 1340),
            UIANode("Text", ":", "", 1361, 1320, 1368, 1340),
            UIANode("Text", "still recording even when not scrolled all the way down", "", 1370, 1320, 1900, 1340),
        ]
        ui._nodes_at = 1e18
        ui.is_connected = lambda: True  # type: ignore[method-assign]
        events = ui.get_chat_events()
        self.assertEqual(len(events), 1)
        self.assertEqual(events[0]["user"], "tsyko")

    def test_realistic_edge_tts_voice_switching(self) -> None:
        ui = CamfrogUIAutomation()
        self.assertEqual(ui.set_tts_voice("andrew"), "en-US-AndrewMultilingualNeural")
        self.assertEqual(ui.set_tts_voice("ava"), "en-US-AvaMultilingualNeural")
        # Coqui labels route to the XTTS engine (sub-menu selection for the SPECIAL MIC LINE).
        from ui_automation import COQUI_DEFAULT_VOICE, COQUI_FEMALE_VOICES, is_coqui_voice

        self.assertEqual(ui.set_tts_voice(COQUI_DEFAULT_VOICE), COQUI_DEFAULT_VOICE)
        self.assertTrue(is_coqui_voice(COQUI_DEFAULT_VOICE))
        self.assertTrue(all(is_coqui_voice(label) for label in COQUI_FEMALE_VOICES))

        # !voice <name> switches the engine voice but posts NO announcement to the room (operator-only).
        sent_before = list(self.ui.sent)
        self.bot._handle_message("Alice_1", "!voice andrew", "2:10 PM")
        self.assertEqual(self.ui.sent, sent_before, "!voice must not announce itself to the chatroom")
        self.assertEqual(self.bot.settings["tts_voice"], "en-US-AndrewMultilingualNeural")

    # --- New Tests for Tasks 1-4 (uia_interface, vision_analyzer, strategy_core, main) ---

    def test_vision_analyzer_parses_pat_outcomes_and_rolling_ev(self) -> None:
        vision = VisionAnalyzer(base_spin_cost_pat=5_000)
        obs = vision.parse_game_result_text([
            "Jackpot Pool: 4,200,000 PAT",
            "You won 20,000 PAT",
            "You lost 5,000 PAT",
            "!beg payout: 6,500 PAT",
        ])
        self.assertEqual(len(obs), 3)
        self.assertEqual(vision.observed_jackpot_pool, 4_200_000)
        metrics = vision.get_rolling_ev_metrics()
        self.assertEqual(metrics.total_spins, 2)
        self.assertEqual(metrics.win_count, 1)
        self.assertEqual(metrics.loss_count, 1)
        # +15,000 (win net) - 5,000 (loss net) + 6,500 (beg net) = +16,500 PAT
        self.assertEqual(metrics.cumulative_net_pat, 16_500)
        # Spin EV = (+15,000 - 5,000) / 2 = +5,000 PAT/spin
        self.assertAlmostEqual(metrics.rolling_ev_per_spin, 5000.0)

    def test_strategy_core_beg_safety_loop_and_3hr_cooldown(self) -> None:
        engine = PepeFrogStrategyEngine(initial_wallet_pat=3_200, initial_jackpot_pat=3_000_000)
        now = 100_000.0
        # Wallet < 5,000 PAT and !beg cooldown ready -> triggers !beg
        decision1 = engine.evaluate_next_action(now_mono=now)
        self.assertEqual(decision1.command, "!beg")
        self.assertEqual(decision1.mode_flag, "SAFETY_BEG")

        # Record !beg with a small 1,000 PAT payout so balance is still 4,200 (< 5,000)
        engine.record_command_execution("!beg", net_delta_pat=1_000, now_mono=now)
        self.assertEqual(engine.wallet_balance_pat, 4_200)
        # 3-hour cooldown should now be enforced (~10,800s remaining)
        self.assertGreater(engine.beg_cooldown_remaining(now + 10.0), BEG_COOLDOWN_SECONDS - 20.0)
        decision2 = engine.evaluate_next_action(now_mono=now + 10.0)
        self.assertIn(decision2.command, {"!lotto", "HOLD"})

    def test_strategy_core_pity_mechanics_and_jackpot_cap(self) -> None:
        engine = PepeFrogStrategyEngine(initial_wallet_pat=60_000, initial_jackpot_pat=4_999_000)
        for _ in range(6):
            engine.record_command_execution("!spin", net_delta_pat=-SPIN_FLAT_COST_PAT, won=False)
        # Jackpot pool is capped at 5,000,000 PAT
        self.assertEqual(engine.jackpot_pool_pat, JACKPOT_POOL_CAP_PAT)
        # 6 consecutive losses activates Sink-Rate Pity Safety Net
        self.assertTrue(engine.pity_state.pity_safety_net_active)
        decision = engine.evaluate_next_action()
        self.assertEqual(decision.command, "!spin")
        self.assertEqual(decision.mode_flag, "PITY_SURGE")

    def test_precision_timer_and_orchestrator_dry_run(self) -> None:
        abort = threading.Event()
        t0 = time.perf_counter()
        ok = precision_sleep_until(t0 + 0.025, abort)
        elapsed = time.perf_counter() - t0
        self.assertTrue(ok)
        self.assertGreaterEqual(elapsed, 0.023)

        orch = PepeFrogOrchestrator(dry_run=True, spin_interval_s=0.05)
        telemetry = orch.step_cycle()
        self.assertIn("wallet_balance_pat", telemetry)
        self.assertGreaterEqual(orch.uia.commands_dispatched, 1)

    def test_heist_parser_and_strongest_character_builder(self) -> None:
        vision = VisionAnalyzer()
        vision.parse_game_result_text([
            "KaeKae_Toad !sheet -> Class: Mastermind | STR 14 DEX 16 CON 15 INT 18 WIS 14 CHA 9 | Unspent Points: 2",
            "Rare drop unlocked: Kingpin's Ring and Loaded Dice!",
            "Forming a casino heist! Type !join to rob the casino!",
            "Round 9/9: Vault door next! Accrued loot: 55,000 PAT | Casino vault: 400,000 PAT",
        ])
        self.assertEqual(vision.heist_state.stats["INT"], 18)
        self.assertEqual(vision.heist_state.stats["CHA"], 9)
        self.assertEqual(vision.heist_state.unspent_stat_points, 2)
        self.assertEqual(vision.heist_state.forming_job, "casino")
        self.assertTrue(vision.heist_state.at_vault_door_window)
        self.assertEqual(vision.heist_state.accrued_loot_pat, 55_000)

        engine = PepeFrogStrategyEngine()
        engine.heist_advisor.stats = dict(vision.heist_state.stats)
        engine.heist_advisor.unspent_points = vision.heist_state.unspent_stat_points
        cmd, _ = engine.heist_advisor.recommend_character_upgrade_command()
        self.assertEqual(cmd, "!allot cha")

        door_act, _ = engine.heist_advisor.evaluate_vault_door_vs_bail(
            job="casino",
            accrued_loot_pat=55_000,
            vault_balance_pat=400_000,
        )
        self.assertIn(door_act, {"!bail", "STAY_FOR_DOOR"})

        orch = PepeFrogOrchestrator(dry_run=True)
        diag = orch.uia.get_setup_diagnostics()
        self.assertTrue(diag["is_right_half_2560x1440"])
        self.assertEqual(diag["window_rect"], (1273, 0, 2567, 1399))

    def test_all_20_kaekae_triggers_and_enhanced_db_schema(self) -> None:
        from main import is_incoming_room_log, is_transcription_log

        # SILENT BOOT: Trigger 1 (kaekae) must NOT reach the room while the bot is silent.
        self.bot._handle_message("Rosie", "I love hitting the jackpot on the wheel", "3:00 PM")
        self.bot._handle_message("Stonerwayne1000", "Kaekae what should we do next?", "3:01 PM")
        self.assertEqual(self.ui.sent, [], "Silent boot must suppress the kaekae trigger reply")

        # Operator flips silent off -> Trigger 1 replies normally (case-insensitive, no ! required)
        self.bot.silent_switch(False)
        self.bot._handle_message("Stonerwayne1000", "Kaekae what should we do next?", "3:01 PM")
        self.assertTrue(any("@Stonerwayne1000" in m for m in self.ui.sent))

        # Trigger 10: !diss never repeats the same diss twice
        d1 = self.bot._pick_unique_diss("Stonerwayne1000")
        d2 = self.bot._pick_unique_diss("Stonerwayne1000")
        self.assertNotEqual(d1, d2)

        # Trigger 11 & 12: !who is & !info on include gender, top noun, text/audio tone, and biography
        self.bot._handle_message("Rosie", "!who is Rosie", "3:02 PM")
        self.assertTrue(any("Biography of Rosie" in m and "female" in m for m in self.ui.sent))

        # Trigger 13: !grabs flexible increments (5m up to 72h)
        self.bot.store.record_mic_grab("OMGitsMyPHONE", "2099-01-01T00:00:00+00:00", 14.0, "Hello lounge")
        res_5m = self.bot._grabs("OMGitsMyPHONE 5m")
        self.assertTrue(any("5 minutes" in r for r in res_5m))
        res_72h = self.bot._grabs("72h")
        self.assertTrue(any("72h" in r for r in res_72h))

        # Trigger 15: !idk smart answer / witty comeback
        idk_res = self.bot._dispatch("Rosie", "!idk 25 + 75")
        self.assertTrue(any("100" in r for r in idk_res))

        # Trigger 16: Moderation history query requires a valid username after trigger words
        self.assertEqual(self.bot._dispatch("Rosie", "who kicked"), [])
        self.assertTrue(len(self.bot._dispatch("Rosie", "who kicked Stonerwayne1000")) == 1)

        # Function/status triggers must NEVER announce themselves to the room (operator terminals only).
        before = list(self.ui.sent)
        self.assertEqual(self.bot._dispatch("Rosie", "!chat"), [])
        self.assertEqual(self.bot._dispatch("Rosie", "!triggers"), [])
        self.assertEqual(self.bot._dispatch("Rosie", "!transcribe"), [])
        self.assertEqual(self.bot._dispatch("Rosie", "!voice aria"), [])
        self.assertEqual(self.ui.sent, before, "Function announcements must not reach the chatroom")

        # Triggers 17, 18, 19: !happy, !sad, !mad tones when !chat is ON (silenced by !chat handler above)
        self.assertTrue(self.bot.settings["chat_mode"])
        self.bot._dispatch("Rosie", "!happy")
        self.assertEqual(self.bot.settings["tone"], "happy")

        # Split terminal routing helpers: Terminal 1 (room feed) vs Terminal 3 (live transcription)
        self.assertTrue(is_incoming_room_log("[10:00:00] [INCOMING CHAT 💬] Rosie: hello"))
        self.assertFalse(is_incoming_room_log("[10:00:00] [SPIN ANALYZER #1 ✅] Outcome=WIN"))
        self.assertTrue(is_transcription_log("[10:00:01] [LIVE-TRANSCRIBE 🎙️] [MIC] Rosie: \"hello lounge\""))
        self.assertFalse(is_incoming_room_log("[10:00:01] [LIVE-TRANSCRIBE 🎙️] [MIC] Rosie: \"hello lounge\""))
        self.assertTrue(is_transcription_log("[10:00:02] [VOICE CLONE 🧬] Building XTTS speaker latent..."))

    def test_compute_device_resolver_prefers_amd_first(self) -> None:
        """resolve_compute_device() must always return the structured AMD->NVIDIA->CPU device dict."""
        dev = resolve_compute_device()
        self.assertIsInstance(dev, dict)
        for key in ("backend", "device", "compute_type", "name", "amd", "nvidia", "gpu"):
            self.assertIn(key, dev)
        self.assertIn(dev["backend"], {"amd-directml", "amd-rocm", "nvidia-cuda", "cpu"})
        # On this AMD-9070XT rig with torch-directml/onnxruntime-directml installed it must pick AMD.
        if dev["gpu"]:
            self.assertTrue(dev["amd"] or dev["nvidia"])
            if dev["amd"]:
                self.assertIn(dev["backend"], {"amd-directml", "amd-rocm"})
        # Priority chain: CPU is always the last resort, never a GPU claim.
        if dev["backend"] == "cpu":
            self.assertFalse(dev["amd"])
            self.assertFalse(dev["nvidia"])
            self.assertFalse(dev["gpu"])

    def test_mic_grab_sequence_matches_operator_spec(self) -> None:
        """3 extremely fast clicks + 4th held; >=1.3s speaker confirmation; retry until full hold."""
        self.assertEqual(MIC_GRAB_FAST_CLICKS, 3)
        self.assertLessEqual(MIC_GRAB_FAST_CLICK_DELAY, 0.05)
        self.assertEqual(MIC_CONFIRM_PERSIST_SECONDS, 1.3)
        self.assertGreaterEqual(MIC_GRAB_HOLD_MIN_SECONDS, 3.0)
        self.assertGreaterEqual(MIC_GRAB_MAX_ATTEMPTS, 3)
        # The mic-grab path must exist on the adapter for the SPECIAL MIC LINE broadcasts.
        self.assertTrue(callable(CamfrogUIAutomation.broadcast_tts_via_vbcable))

    def test_voice_catalogs_are_female_only_with_default_last(self) -> None:
        """SPECIAL MIC LINE sub-menus: Edge = women only; Coqui = women + Default(test) + CLONE slot last."""
        edge_values = edge_female_voice_catalog()
        self.assertEqual(edge_values, list(EDGE_FEMALE_VOICES.keys()))
        self.assertTrue(all(v.startswith("Edge ") for v in edge_values))
        # No male Edge voices leak into the sub-menu.
        for male in ("Guy", "Andrew", "Brian", "Christopher", "Steffan", "Ryan"):
            self.assertFalse(any(male in v for v in edge_values))
        coqui_values = coqui_voice_catalog()
        self.assertEqual(coqui_values, list(COQUI_FEMALE_VOICES.keys()) + [COQUI_DEFAULT_VOICE, COQUI_CLONE_VOICE])
        # The ONLY non-woman entry is Coqui Default (used to test cloning) + the dynamic CLONE slot.
        self.assertEqual(coqui_values[-2], COQUI_DEFAULT_VOICE)
        self.assertEqual(coqui_values[-1], COQUI_CLONE_VOICE)
        for label in coqui_values:
            self.assertTrue(is_coqui_voice(label))

    def test_coqui_clone_state_machine_sample_clone_default_clear(self) -> None:
        """Sample -> Clone -> Default -> CLR Voice drives engine state (no heavy model needed offline)."""
        eng = CoquiXTTSVoiceEngine()
        status = eng.status()
        self.assertIn("clone_ready", status)
        self.assertIn("clone_is_default", status)
        self.assertFalse(status["clone_ready"])
        self.assertFalse(status["clone_is_default"])
        self.assertEqual(eng.clone_slot_label(), COQUI_CLONE_EMPTY)
        # Default without a verified clone must fail gracefully (never raise).
        logs: list[str] = []
        self.assertFalse(eng.set_clone_as_default(log=logs.append))
        # Clear always succeeds and resets to the built-in test voice.
        self.assertTrue(eng.clear_default_voice(log=logs.append))
        self.assertFalse(eng._clone_is_default)
        # Simulate a verified clone -> slot flips to Active, Default routes the clone.
        eng._sample_wav = str(Path(__file__).parent / "test_bot.py")  # any existing file for the copy path
        eng._clone_reference_wav = eng._sample_wav
        eng._clone_ready = True
        self.assertEqual(eng.clone_slot_label(), COQUI_CLONE_VOICE)
        self.assertTrue(eng.set_clone_as_default(log=logs.append))
        self.assertTrue(eng._clone_is_default)
        self.assertTrue(any("[DEFAULT" in line for line in logs))
        if not eng.is_available():
            ok, engine = eng.synthesize("hello", Path(self.temp.name) / "t.wav", COQUI_DEFAULT_VOICE, log=logs.append)
            self.assertFalse(ok)
            self.assertTrue(str(engine).startswith("coqui-unavailable"))
        # Adapter wires the engine + label routing used by the SPECIAL MIC LINE.
        ui = CamfrogUIAutomation()
        self.assertIsInstance(ui.coqui, CoquiXTTSVoiceEngine)
        self.assertEqual(ui.set_tts_voice(COQUI_CLONE_VOICE), COQUI_CLONE_VOICE)
        self.assertEqual(ui.tts_voice_label, COQUI_CLONE_VOICE)

    def test_kokoro_voice_catalog_female_only_with_default_last(self) -> None:
        """SPECIAL MIC LINE Local GPU sub-menu: Kokoro = women only + Kokoro Default (Test) last."""
        kok_values = kokoro_voice_catalog()
        self.assertEqual(kok_values, list(KOKORO_FEMALE_VOICES.keys()) + [KOKORO_DEFAULT_VOICE])
        self.assertTrue(all(v.startswith("Kokoro ") for v in kok_values))
        # The ONLY non-woman entry is Kokoro Default (used purely to verify the pipeline).
        self.assertEqual(kok_values[-1], KOKORO_DEFAULT_VOICE)
        for label in kok_values:
            self.assertTrue(is_kokoro_voice(label))
        # No male Kokoro voice ids leak in (af_/bf_ are female; am_/bm_ would be male).
        for vid in KOKORO_FEMALE_VOICES.values():
            self.assertTrue(vid.startswith("af_") or vid.startswith("bf_"), f"non-female id {vid}")

    def test_kokoro_engine_lazy_and_sentinel_when_assets_missing(self) -> None:
        """LocalKokoroVoiceEngine is import-safe; synthesize returns a fallback sentinel offline."""
        eng = LocalKokoroVoiceEngine()
        status = eng.status()
        self.assertIn("available", status)
        self.assertIn("loaded", status)
        self.assertIn("device", status)
        self.assertFalse(status["loaded"])  # never heavy-loads on construct
        # When ONNX assets aren't present, synthesize must NOT raise — it returns a sentinel
        # so the caller falls through to Coqui -> Edge and the mic still broadcasts.
        logs: list[str] = []
        if not eng.is_available():
            ok, engine = eng.synthesize("hello", Path(self.temp.name) / "k.wav", KOKORO_DEFAULT_VOICE, log=logs.append)
            self.assertFalse(ok)
            self.assertTrue(str(engine).startswith("kokoro-unavailable"))

    def test_kokoro_adapter_wiring_and_priority(self) -> None:
        """Adapter exposes the Kokoro engine and routes Kokoro labels to it (before Coqui/Edge)."""
        ui = CamfrogUIAutomation()
        self.assertIsInstance(ui.kokoro, LocalKokoroVoiceEngine)
        # A Kokoro label sets tts_voice_label and is recognized as a Kokoro selection.
        self.assertEqual(ui.set_tts_voice("Kokoro Heart"), "Kokoro Heart")
        self.assertEqual(ui.tts_voice_label, "Kokoro Heart")
        self.assertTrue(is_kokoro_voice("Kokoro Heart"))
        # Edge + Coqui labels must NOT be mistaken for Kokoro (mutually exclusive routing).
        self.assertFalse(is_kokoro_voice(COQUI_DEFAULT_VOICE))
        self.assertFalse(is_kokoro_voice("Edge Aria"))
        # Kokoro and Coqui namespaces never overlap.
        self.assertFalse(any(is_coqui_voice(v) for v in kokoro_voice_catalog()))
        self.assertFalse(any(is_kokoro_voice(v) for v in coqui_voice_catalog()))

    def test_kokoro_provider_strategy_and_gpu_toggle(self) -> None:
        """Kokoro engine: CPU-default, GPU opt-in toggle, auto provider status (no heavy load)."""
        eng = LocalKokoroVoiceEngine()
        # Default is CPU (stability-first); GPU is opt-in, never forced.
        self.assertFalse(eng._prefer_gpu)
        self.assertEqual(eng._active_provider, "")
        # gpu_available() reflects the onnxruntime build without loading the model.
        self.assertIsInstance(eng.gpu_available(), bool)
        # set_prefer_gpu flips the preference and drops any cached session for reload.
        eng.set_prefer_gpu(True)
        self.assertTrue(eng._prefer_gpu)
        self.assertIsNone(eng._kokoro)
        eng.set_prefer_gpu(False)
        self.assertFalse(eng._prefer_gpu)
        # status() surfaces the new fields for the GUI/diagnostics.
        st = eng.status()
        for key in ("provider", "prefer_gpu", "gpu_available"):
            self.assertIn(key, st)

    def test_xtts_local_wrapper_synthesis_api(self) -> None:
        """_XttsLocalWrapper exposes the tts_to_file / tts_with_vc_to_file API the engine calls."""
        from ui_automation import _XttsLocalWrapper

        calls: list[tuple] = []

        class _FakeModel:
            speaker_manager = None

            def full_inference(self, text, ref_audio_path, language):
                calls.append(("vc", text, ref_audio_path))
                return {"wav": [0.0, 0.5, -0.5, 0.1]}

            def inference(self, text, language, gpt_cond_latent, speaker_embedding):
                calls.append(("named", text))
                return [0.0, 0.2, -0.2]

        wrap = _XttsLocalWrapper(_FakeModel())
        self.assertTrue(hasattr(wrap, "tts_with_vc_to_file"))
        self.assertTrue(hasattr(wrap, "tts_to_file"))
        out = Path(self.temp.name) / "wrap.wav"
        # Voice-clone path writes a valid 16-bit PCM wav from the fake model output.
        wrap.tts_with_vc_to_file(text="hi", speaker_wav="ref.wav", file_path=str(out), language="en")
        self.assertTrue(out.exists() and out.stat().st_size > 44)
        with wave.open(str(out), "rb") as wf:
            self.assertEqual(wf.getnchannels(), 1)
            self.assertEqual(wf.getsampwidth(), 2)
            self.assertGreater(wf.getnframes(), 0)
        self.assertTrue(any(c[0] == "vc" for c in calls))


    def test_rounded_button_gui_factory(self) -> None:
        """App buttons render through make_rounded_btn (rounded corners + tk.Button-compatible API)."""
        import main as main_mod

        self.assertTrue(callable(main_mod.make_rounded_btn))
        if not getattr(main_mod, "TK_GUI_AVAILABLE", False):
            self.skipTest("Tkinter unavailable in this environment")
        root = main_mod.tk.Tk()
        root.withdraw()
        try:
            frame = main_mod.tk.Frame(root, bg="#0B1120")
            clicks: list[int] = []
            btn = main_mod.make_rounded_btn(
                frame,
                text="Rounded",
                bg="#10B981",
                fg="#FFFFFF",
                activebackground="#34D399",
                font=("Segoe UI", 8, "bold"),
                padx=8,
                pady=3,
                relief="flat",
                bd=0,
                highlightthickness=1,
                highlightbackground="#334155",
                cursor="hand2",
                command=lambda: clicks.append(1),
            )
            self.assertIsInstance(btn, main_mod.RoundedButton)
            btn.config(text="ON", bg="#EF4444", fg="#000000")
            btn._on_press(None)
            btn._on_release(None)
            self.assertEqual(clicks, [1])
            btn.configure(state="disabled")
            clicks.clear()
            btn._on_press(None)
            btn._on_release(None)
            self.assertEqual(clicks, [], "disabled buttons must not fire their command")
        finally:
            root.destroy()


if __name__ == "__main__":
    unittest.main(verbosity=2)


