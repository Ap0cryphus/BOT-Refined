"""
vision_analyzer.py — Task 2: Computer Vision, Heist/Game Chat Parser & Spin Timing Engine
=========================================================================================

Visual & Chat Stream Monitor Engine for `publicaccess.tv` (PepeFrog) inside Camfrog:
1. Bounds target frame overlay regions highlighting the "Spin the Wheel" graphic module
   (`SPIN_WHEEL_ROI = (1281, 170, 2355, 780)`) and Chat Result feed (`CHAT_RESULT_ROI = (1281, 780, 2355, 1160)`).
2. Uses OpenCV (`cv2`), NumPy (`np`), and PyAutoGUI (`pyautogui`) alongside built-in Camfrog UIA chat
   events to pull immediate game-result text alerts across ALL PepeFrog games:
   - Wheel of Misfortune (`!spin`): `"You won 25,000 PAT"`, `"GOLDEN SLICE JACKPOT"`, `"You lost 5,000 PAT"`,
     `"Slow down!"`, plus phase-bucket timing telemetry to learn which timing window yields the highest win/jackpot rate.
   - Grand Theft Frogger Heists (`!heist store|casino|convoy|bank`, `!bail`, `!sheet`, `!allot`, `!ring`, `!reroll`, `!shop`, `!buy`):
     Parses live Camfrog chat heist status, character sheet 6 D&D stats (`STR`, `DEX`, `CON`, `INT`, `WIS`, `CHA`),
     rare relic drops (`Blueprints`, `Loaded Dice`, `Kingpin's Ring`, `The Fence`, `Mastermind`), round progression,
     and the critical pre-vault-door `!bail` window.
   - All `publicaccess.tv/help#cat-games` modules (`!beg`, `!lotto`, `!bingo`, `!trivia`, `!showdown`, `!arena`, `!brawl`, `!duel`, `!bj`, `!holdem`).
3. Connects visual and chat cues directly into a rolling Expected Value (EV) & Spin Timing Optimizer database array.
"""

from __future__ import annotations

import re
import time
from collections import deque
from dataclasses import asdict, dataclass, field
from typing import Any, Callable

# Graceful imports so unit tests and headless environments work even before OpenCV/PyAutoGUI finish installing
try:
    import numpy as np
except ImportError:
    np = None  # type: ignore[assignment]

try:
    import cv2  # type: ignore[import-not-found]
except ImportError:
    cv2 = None  # type: ignore[assignment]

try:
    import pyautogui  # type: ignore[import-not-found]
    pyautogui.FAILSAFE = False
except ImportError:
    pyautogui = None  # type: ignore[assignment]


# Regex patterns for PepeFrog (publicaccess.tv) stream economy alerts in Camfrog chat
_WIN_PAT_RE = re.compile(
    r"(?:"
    r"(?:you\s+won|won|wins|winner|payout|rewarded|landed\s+on\s+win|landed\s+on|collected|wheel\s+paid|paid\s+out|hit\s+for|scored|spun\s+and\s+won|takes\s+home)\s*[:+\-!$]*\s*([\d,]+)\s*(?:PAT|pts|points|coins)?"
    r"|"
    r"\+\s*([\d,]+)\s*PAT\b"
    r")",
    re.IGNORECASE,
)
_LOSS_PAT_RE = re.compile(
    r"(?:"
    r"(?:you\s+lost|lost|loses|bust|busted|misfortune|bankrupt|deducted|better\s+luck|nothing|no\s+win|whiffed|skull|spun\s+and\s+lost)\s*[:+\-!$]*\s*([\d,]+)?\s*(?:PAT)?"
    r"|"
    r"-\s*([\d,]+)\s*PAT\b"
    r")",
    re.IGNORECASE,
)
_JACKPOT_POOL_RE = re.compile(
    r"(?:jackpot(?:\s+pool|\s+balance|\s+vault|\s+is|\s+at)?|golden\s+slice|casino\s+jackpot|wheel\s+jackpot|pot\s+is)\s*[:=\-$]*\s*([\d,]+)\s*(?:PAT)?",
    re.IGNORECASE,
)
_CASINO_VAULT_RE = re.compile(
    r"(?:casino\s+vault)\s*[:=\-]*\s*([\d,]+)\s*PAT",
    re.IGNORECASE,
)
_FED_RESERVE_RE = re.compile(
    r"(?:federal\s+reserve|reserve\s+vault|bank\s+vault)\s*[:=\-]*\s*([\d,]+)\s*PAT",
    re.IGNORECASE,
)
_BALANCE_PAT_RE = re.compile(
    r"(?:balance|wallet|total\s+pat|pat\s+balance|you\s+have|bankroll)\s*[:=\-$]*\s*([\d,]+)\s*(?:PAT)?",
    re.IGNORECASE,
)
_BEG_PAYOUT_RE = re.compile(
    r"(?:!beg|begged|handout|charity|pity\s+drop|spare\s+change)[^0-9]*([\d,]+)\s*(?:PAT)?",
    re.IGNORECASE,
)
_COOLDOWN_ALERT_RE = re.compile(
    r"(?:slow\s+down|cooldown|wait\s+(\d+(?:\.\d+)?)\s*s|already\s+spinning)",
    re.IGNORECASE,
)

# Heist & Character Sheet regex patterns (`publicaccess.tv/help#cat-heists`)
_SHEET_STAT_RE = re.compile(
    r"\b(STR|DEX|CON|INT|WIS|CHA)\s*[:=\-]?\s*(\d{1,2})\b",
    re.IGNORECASE,
)
_SHEET_POINTS_RE = re.compile(
    r"(?:unspent|available|stat|allot)\s+points?\s*[:=\-]?\s*(\d{1,2})|(\d{1,2})\s+points?\s+to\s+(?:spend|allot)",
    re.IGNORECASE,
)
_SHEET_CLASS_RE = re.compile(
    r"\bclass\s*[:=\-]\s*([A-Za-z_ -]{3,24})",
    re.IGNORECASE,
)
_HEIST_RELIC_RE = re.compile(
    r"(Blueprints|Loaded\s+Dice|Kingpin'?s\s+Ring|The\s+Fence|Mastermind)",
    re.IGNORECASE,
)
_HEIST_ROUND_RE = re.compile(
    r"round\s+(\d{1,2})\s*(?:/|of)\s*(\d{1,2})",
    re.IGNORECASE,
)
_HEIST_LOOT_RE = re.compile(
    r"(?:accrued\s+loot|holding|banked\s+loot|crew\s+loot|loot\s+so\s+far)\s*[:=\-]*\s*([\d,]+)\s*PAT",
    re.IGNORECASE,
)
_HEIST_FORMING_RE = re.compile(
    r"(?:heist\s+on\s+the\s+(store|casino|convoy|bank)|forming\s+a\s+(store|casino|convoy|bank)\s+heist|!join\s+to\s+rob\s+the\s+(store|casino|convoy|bank))",
    re.IGNORECASE,
)
_CONVOY_ROAD_RE = re.compile(
    r"(?:armored\s+convoy|convoy\s+leaves|convoy\s+on\s+the\s+road|!heist\s+convoy)",
    re.IGNORECASE,
)
_VAULT_DOOR_WARNING_RE = re.compile(
    r"(?:vault\s+door\s+next|last\s+!bail\s+window|before\s+the\s+door|approaching\s+the\s+vault\s+door)",
    re.IGNORECASE,
)

# Multi-game lobby detection (`cat-games`)
_BINGO_CALLED_RE = re.compile(
    r"(?:bingo\s+line|complete\s+line|has\s+a\s+line|call\s+!bingo\s+now)",
    re.IGNORECASE,
)
_TRIVIA_LOBBY_RE = re.compile(
    r"(?:trivia\s+lobby\s+open|!join\s+to\s+play\s+trivia)",
    re.IGNORECASE,
)
_SHOWDOWN_START_RE = re.compile(
    r"(?:showdown\s+started|secret\s+number\s+from\s+1\s+to\s+10,?000|type\s+!guess)",
    re.IGNORECASE,
)
_ARENA_LOBBY_RE = re.compile(
    r"(?:opened\s+the\s+arena|arena\s+battle\s+royale|!join\s+the\s+arena)",
    re.IGNORECASE,
)


def _parse_pat_int(raw_digits: str | None, default: int = 0) -> int:
    if not raw_digits:
        return default
    cleaned = re.sub(r"[^\d]", "", str(raw_digits))
    return int(cleaned) if cleaned else default


@dataclass
class SpinVisualObservation:
    """Single parsed visual / chat observation from the Spin the Wheel or Heist modules."""

    timestamp: float
    raw_text: str
    outcome: str  # "win" | "loss" | "jackpot" | "beg" | "cooldown" | "heist" | "game_event"
    gross_payout_pat: int = 0
    wager_cost_pat: int = 5_000
    net_delta_pat: int = 0
    detected_jackpot_pool: int | None = None
    detected_wallet_balance: int | None = None
    wheel_motion_energy: float = 0.0
    gold_slice_ratio: float = 0.0
    spin_timing_offset_ms: int = 200


@dataclass
class HeistLiveState:
    """Live parsed state of Grand Theft Frogger (`!heist` & `!sheet`) from Camfrog chat."""

    character_class: str = "Mastermind"
    stats: dict[str, int] = field(
        default_factory=lambda: {"STR": 14, "DEX": 16, "CON": 15, "INT": 18, "WIS": 14, "CHA": 13}
    )
    unspent_stat_points: int = 0
    relics_owned: list[str] = field(default_factory=lambda: ["Blueprints", "Kingpin's Ring"])
    gear_owned: list[str] = field(
        default_factory=lambda: ["Good Lawyer", "Ghost Plates", "Schematics", "Lockpick", "Hacking Rig"]
    )
    active_job: str | None = None          # "store" | "casino" | "convoy" | "bank"
    forming_job: str | None = None         # "store" | "casino" | "convoy" | "bank"
    convoy_available: bool = False
    current_round: int = 0
    total_rounds: int = 0
    at_vault_door_window: bool = False
    accrued_loot_pat: int = 0
    casino_vault_pat: int = 650_000
    federal_reserve_pat: int = 2_400_000
    last_heist_alert: str = "Ready to scan !sheet and !heist events in Camfrog chat."


@dataclass
class RollingEVMetrics:
    """Rolling Expected Value (EV) database array & Spin Timing Optimizer summary."""

    sample_count: int = 0
    total_spins: int = 0
    win_count: int = 0
    loss_count: int = 0
    jackpot_hits: int = 0
    cumulative_net_pat: int = 0
    rolling_ev_per_spin: float = 0.0
    rolling_win_rate: float = 0.0
    net_yield_per_hour_pat: float = 0.0
    observed_jackpot_pool: int = 2_500_000
    optimal_timing_offset_ms: int = 200
    best_bucket_win_rate: float = 0.0
    recent_deltas: list[int] = field(default_factory=list)


class VisionAnalyzer:
    """OpenCV + NumPy + PyAutoGUI visual monitor, Heist/Game Chat Parser, and Spin Timing Optimizer."""

    def __init__(
        self,
        *,
        wheel_roi: tuple[int, int, int, int] = (1281, 170, 2355, 780),
        result_roi: tuple[int, int, int, int] = (1281, 780, 2355, 1160),
        rolling_window_size: int = 250,
        base_spin_cost_pat: int = 5_000,
        ocr_provider: Callable[[int, int, int, int], list[str]] | None = None,
    ) -> None:
        self.wheel_roi = wheel_roi      # (left, top, right, bottom)
        self.result_roi = result_roi    # (left, top, right, bottom)
        self.base_spin_cost_pat = base_spin_cost_pat
        self._ocr_provider = ocr_provider

        # Rolling Expected Value (EV) database array
        self.ev_database: deque[SpinVisualObservation] = deque(maxlen=max(10, rolling_window_size))
        self._prev_wheel_gray: Any = None
        self._session_started_mono: float = time.perf_counter()
        self.observed_jackpot_pool: int = 2_500_000
        self.observed_wallet_balance: int | None = None
        self.last_cooldown_warning_at: float = 0.0

        # Spin Timing Buckets (ms offset past 20.0s cooldown: 150ms, 200ms, 280ms, 360ms, 450ms)
        self.timing_buckets: dict[int, dict[str, int]] = {
            150: {"spins": 0, "wins": 0, "jackpots": 0, "net_pat": 0},
            200: {"spins": 0, "wins": 0, "jackpots": 0, "net_pat": 0},
            280: {"spins": 0, "wins": 0, "jackpots": 0, "net_pat": 0},
            360: {"spins": 0, "wins": 0, "jackpots": 0, "net_pat": 0},
            450: {"spins": 0, "wins": 0, "jackpots": 0, "net_pat": 0},
        }
        self.last_spin_offset_ms: int = 200

        # Live Heist & Multi-Game state parsed from Camfrog chat
        self.heist_state = HeistLiveState()
        self.pending_game_triggers: deque[str] = deque(maxlen=25)

    def select_optimal_spin_offset_ms(self) -> int:
        """UCB1 / Thompson-inspired timing bucket selector that tests timing offsets (150ms..450ms)
        and locks onto the phase window producing the highest win percentage and jackpot hits.
        """
        # First explore any bucket with < 2 spins so we test timings across the wheel phase
        for offset_ms, stats in self.timing_buckets.items():
            if stats["spins"] < 2:
                self.last_spin_offset_ms = offset_ms
                return offset_ms

        best_offset = 200
        best_score = -1e9
        for offset_ms, stats in self.timing_buckets.items():
            spins = max(1, stats["spins"])
            win_rate = stats["wins"] / float(spins)
            avg_net = stats["net_pat"] / float(spins)
            jackpot_bonus = stats["jackpots"] * 0.35
            score = (win_rate * 100.0) + (avg_net / 500.0) + jackpot_bonus
            if score > best_score:
                best_score = score
                best_offset = offset_ms

        self.last_spin_offset_ms = best_offset
        return best_offset

    def record_spin_timing_outcome(self, offset_ms: int, *, won: bool, is_jackpot: bool, net_delta_pat: int) -> None:
        bucket = min(self.timing_buckets.keys(), key=lambda k: abs(k - offset_ms))
        entry = self.timing_buckets[bucket]
        entry["spins"] += 1
        if won:
            entry["wins"] += 1
        if is_jackpot:
            entry["jackpots"] += 1
        entry["net_pat"] += int(net_delta_pat)

    def capture_roi_bgr(self, roi: tuple[int, int, int, int]) -> Any:
        """Capture target screen region `(left, top, right, bottom)` as a NumPy BGR frame with overlay bounding box."""
        if np is None or pyautogui is None:
            return None
        left, top, right, bottom = roi
        width = max(16, right - left)
        height = max(16, bottom - top)
        try:
            pil_img = pyautogui.screenshot(region=(left, top, width, height))
            rgb = np.array(pil_img)
            if cv2 is not None:
                bgr = cv2.cvtColor(rgb, cv2.COLOR_RGB2BGR)
                cv2.rectangle(bgr, (2, 2), (width - 3, height - 3), (0, 215, 255), 2)
                return bgr
            return rgb
        except Exception:
            return None

    def analyze_wheel_frame(self, frame_bgr: Any = None) -> tuple[float, float]:
        """Compute structural frame-to-frame motion energy and golden jackpot slice pixel ratio via OpenCV HSV mask."""
        if frame_bgr is None:
            frame_bgr = self.capture_roi_bgr(self.wheel_roi)
        if frame_bgr is None or np is None:
            return 0.0, 0.0

        motion_energy = 0.0
        gold_ratio = 0.0
        try:
            if cv2 is not None:
                gray = cv2.cvtColor(frame_bgr, cv2.COLOR_BGR2GRAY)
                if self._prev_wheel_gray is not None and self._prev_wheel_gray.shape == gray.shape:
                    diff = cv2.absdiff(self._prev_wheel_gray, gray)
                    motion_energy = float(np.mean(diff))
                self._prev_wheel_gray = gray

                # Detect golden jackpot slice pixels in HSV space (Hue 18..35, High Saturation/Value)
                hsv = cv2.cvtColor(frame_bgr, cv2.COLOR_BGR2HSV)
                lower_gold = np.array([18, 110, 140], dtype=np.uint8)
                upper_gold = np.array([35, 255, 255], dtype=np.uint8)
                mask = cv2.inRange(hsv, lower_gold, upper_gold)
                gold_ratio = float(np.count_nonzero(mask)) / float(mask.size or 1)
            else:
                gold_ratio = 0.01
        except Exception:
            pass
        return motion_energy, gold_ratio

    def _parse_heist_and_games_line(self, line: str) -> None:
        """Parse Grand Theft Frogger (`!heist`, `!sheet`, `!vault`) and multi-game triggers from Camfrog chat."""
        # 1. Character Sheet 6 D&D stats (STR, DEX, CON, INT, WIS, CHA)
        stat_matches = _SHEET_STAT_RE.findall(line)
        if stat_matches:
            for stat_name, val_str in stat_matches:
                val = max(1, min(20, int(val_str)))
                self.heist_state.stats[stat_name.upper()] = val
            self.heist_state.last_heist_alert = f"Parsed !sheet stats: {self.heist_state.stats}"

        pts_match = _SHEET_POINTS_RE.search(line)
        if pts_match:
            raw_pts = pts_match.group(1) or pts_match.group(2)
            self.heist_state.unspent_stat_points = int(raw_pts)

        cls_match = _SHEET_CLASS_RE.search(line)
        if cls_match:
            self.heist_state.character_class = cls_match.group(1).strip()

        # 2. Rare heist relics dropped or listed on !sheet
        for relic_match in _HEIST_RELIC_RE.finditer(line):
            relic_raw = relic_match.group(1).strip()
            norm_relic = "Kingpin's Ring" if "ring" in relic_raw.lower() else relic_raw.title()
            if norm_relic not in self.heist_state.relics_owned:
                self.heist_state.relics_owned.append(norm_relic)
                self.heist_state.last_heist_alert = f"Rare Heist Relic unlocked: {norm_relic}!"

        # 3. Vault balances (!vault / !reserve)
        cv_match = _CASINO_VAULT_RE.search(line)
        if cv_match:
            self.heist_state.casino_vault_pat = _parse_pat_int(cv_match.group(1), self.heist_state.casino_vault_pat)
        fr_match = _FED_RESERVE_RE.search(line)
        if fr_match:
            self.heist_state.federal_reserve_pat = _parse_pat_int(fr_match.group(1), self.heist_state.federal_reserve_pat)

        # 4. Active Heist Round & Vault Door / !bail detection
        form_match = _HEIST_FORMING_RE.search(line)
        if form_match:
            job = (form_match.group(1) or form_match.group(2) or form_match.group(3) or "casino").lower()
            self.heist_state.forming_job = job
            self.heist_state.last_heist_alert = f"Heist crew forming for '{job.upper()}' — ready to !join!"

        if _CONVOY_ROAD_RE.search(line):
            self.heist_state.convoy_available = True
            self.heist_state.last_heist_alert = "Armored Convoy on the road (15m window) — !heist convoy available!"

        rd_match = _HEIST_ROUND_RE.search(line)
        if rd_match:
            cur_r, tot_r = int(rd_match.group(1)), int(rd_match.group(2))
            self.heist_state.current_round = cur_r
            self.heist_state.total_rounds = tot_r
            self.heist_state.active_job = "bank" if tot_r >= 11 else ("casino" if tot_r >= 9 else "store")
            if cur_r >= tot_r:
                self.heist_state.at_vault_door_window = True
                self.heist_state.last_heist_alert = (
                    f"CRITICAL HEIST ROUND {cur_r}/{tot_r}: Approaching Vault Door! Evaluate !bail vs Door risk."
                )

        if _VAULT_DOOR_WARNING_RE.search(line):
            self.heist_state.at_vault_door_window = True
            self.heist_state.last_heist_alert = "Final !bail window before Vault Door detected!"

        loot_match = _HEIST_LOOT_RE.search(line)
        if loot_match:
            self.heist_state.accrued_loot_pat = _parse_pat_int(loot_match.group(1), self.heist_state.accrued_loot_pat)

        # 5. Other PepeFrog games (`cat-games`)
        if _BINGO_CALLED_RE.search(line):
            self.pending_game_triggers.append("!bingo")
        if _TRIVIA_LOBBY_RE.search(line):
            self.pending_game_triggers.append("!join")
        if _SHOWDOWN_START_RE.search(line):
            self.pending_game_triggers.append("!guess 5000")
        if _ARENA_LOBBY_RE.search(line):
            self.pending_game_triggers.append("!join")

    def parse_game_result_text(
        self,
        text_lines: list[str] | str,
        *,
        wager_cost_pat: int | None = None,
    ) -> list[SpinVisualObservation]:
        """Parse OCR or Camfrog UIA chat alerts (`You won X PAT`, `!heist`, `!sheet`, `!beg`) and update EV + Timing DB."""
        if isinstance(text_lines, str):
            lines = [ln.strip() for ln in text_lines.splitlines() if ln.strip()]
        else:
            lines = [str(ln).strip() for ln in text_lines if str(ln).strip()]

        cost = self.base_spin_cost_pat if wager_cost_pat is None else int(wager_cost_pat)
        motion_energy, gold_ratio = self.analyze_wheel_frame(None)
        observations: list[SpinVisualObservation] = []
        now = time.time()

        for line in lines:
            # Always feed line through the Heist & Multi-Game parser
            self._parse_heist_and_games_line(line)

            # 1. Check Jackpot pool balance updates
            jp_match = _JACKPOT_POOL_RE.search(line)
            detected_jp: int | None = None
            if jp_match:
                detected_jp = min(5_000_000, max(0, _parse_pat_int(jp_match.group(1), self.observed_jackpot_pool)))
                self.observed_jackpot_pool = detected_jp

            # 2. Check user wallet balance updates
            bal_match = _BALANCE_PAT_RE.search(line)
            detected_bal: int | None = None
            if bal_match:
                detected_bal = _parse_pat_int(bal_match.group(1), 0)
                self.observed_wallet_balance = detected_bal

            # 3. Check Cooldown / "Slow down!" server rejection
            if _COOLDOWN_ALERT_RE.search(line):
                self.last_cooldown_warning_at = time.perf_counter()
                obs = SpinVisualObservation(
                    timestamp=now,
                    raw_text=line,
                    outcome="cooldown",
                    gross_payout_pat=0,
                    wager_cost_pat=0,
                    net_delta_pat=0,
                    detected_jackpot_pool=detected_jp,
                    detected_wallet_balance=detected_bal,
                    wheel_motion_energy=motion_energy,
                    gold_slice_ratio=gold_ratio,
                    spin_timing_offset_ms=self.last_spin_offset_ms,
                )
                observations.append(obs)
                continue

            # 4. Check !beg random payout (0 - 10,000 PAT, zero wager cost)
            beg_match = _BEG_PAYOUT_RE.search(line)
            if beg_match and "won" not in line.lower():
                payout = min(10_000, max(0, _parse_pat_int(beg_match.group(1), 0)))
                obs = SpinVisualObservation(
                    timestamp=now,
                    raw_text=line,
                    outcome="beg",
                    gross_payout_pat=payout,
                    wager_cost_pat=0,
                    net_delta_pat=payout,
                    detected_jackpot_pool=detected_jp,
                    detected_wallet_balance=detected_bal,
                    wheel_motion_energy=motion_energy,
                    gold_slice_ratio=gold_ratio,
                    spin_timing_offset_ms=self.last_spin_offset_ms,
                )
                self.ev_database.append(obs)
                observations.append(obs)
                continue

            # 5. Check Win / Jackpot result ("You won X PAT", "+X PAT", etc.)
            win_match = _WIN_PAT_RE.search(line)
            if win_match:
                raw_win_num = next((g for g in win_match.groups() if g is not None), "0")
                gross = _parse_pat_int(raw_win_num, 0)
                is_jackpot = gross >= 250_000 or "jackpot" in line.lower() or "gold slice" in line.lower()
                net_delta = gross - cost
                self.record_spin_timing_outcome(
                    self.last_spin_offset_ms,
                    won=True,
                    is_jackpot=is_jackpot,
                    net_delta_pat=net_delta,
                )
                obs = SpinVisualObservation(
                    timestamp=now,
                    raw_text=line,
                    outcome="jackpot" if is_jackpot else "win",
                    gross_payout_pat=gross,
                    wager_cost_pat=cost,
                    net_delta_pat=net_delta,
                    detected_jackpot_pool=detected_jp,
                    detected_wallet_balance=detected_bal,
                    wheel_motion_energy=motion_energy,
                    gold_slice_ratio=gold_ratio,
                    spin_timing_offset_ms=self.last_spin_offset_ms,
                )
                self.ev_database.append(obs)
                observations.append(obs)
                continue

            # 6. Check Loss / Bust result ("You lost 5,000 PAT", "-5,000 PAT", or "Wheel of Misfortune: BUST")
            loss_match = _LOSS_PAT_RE.search(line)
            if loss_match:
                raw_loss_num = next((g for g in loss_match.groups() if g is not None), None)
                lost_amt = _parse_pat_int(raw_loss_num, cost) or cost
                self.record_spin_timing_outcome(
                    self.last_spin_offset_ms,
                    won=False,
                    is_jackpot=False,
                    net_delta_pat=-lost_amt,
                )
                obs = SpinVisualObservation(
                    timestamp=now,
                    raw_text=line,
                    outcome="loss",
                    gross_payout_pat=0,
                    wager_cost_pat=lost_amt,
                    net_delta_pat=-lost_amt,
                    detected_jackpot_pool=detected_jp,
                    detected_wallet_balance=detected_bal,
                    wheel_motion_energy=motion_energy,
                    gold_slice_ratio=gold_ratio,
                    spin_timing_offset_ms=self.last_spin_offset_ms,
                )
                self.ev_database.append(obs)
                observations.append(obs)

        return observations

    def scan_live_screen(self) -> list[SpinVisualObservation]:
        """Run OCR scan on the result overlay region if an OCR provider is attached."""
        if self._ocr_provider is None:
            return []
        l, t, r, b = self.result_roi
        lines = self._ocr_provider(l, t, r, b)
        return self.parse_game_result_text(lines)

    def get_rolling_ev_metrics(self) -> RollingEVMetrics:
        """Compute rolling Expected Value (EV), win rate, optimal timing offset, and net PAT/hour yield."""
        spin_records = [r for r in self.ev_database if r.outcome in {"win", "loss", "jackpot"}]
        all_records = list(self.ev_database)
        total_spins = len(spin_records)
        win_count = sum(1 for r in spin_records if r.outcome in {"win", "jackpot"})
        jackpot_hits = sum(1 for r in spin_records if r.outcome == "jackpot")
        loss_count = sum(1 for r in spin_records if r.outcome == "loss")
        cumulative_net = sum(r.net_delta_pat for r in all_records)

        ev_per_spin = (
            sum(r.net_delta_pat for r in spin_records) / float(total_spins)
            if total_spins > 0
            else 0.0
        )
        win_rate = (win_count / float(total_spins)) if total_spins > 0 else 0.0
        elapsed_hours = max(1e-3, (time.perf_counter() - self._session_started_mono) / 3600.0)
        net_per_hour = cumulative_net / elapsed_hours

        best_offset = self.select_optimal_spin_offset_ms()
        b_stats = self.timing_buckets.get(best_offset, {"spins": 0, "wins": 0})
        best_bucket_wr = (b_stats["wins"] / float(b_stats["spins"])) if b_stats["spins"] > 0 else win_rate

        return RollingEVMetrics(
            sample_count=len(all_records),
            total_spins=total_spins,
            win_count=win_count,
            loss_count=loss_count,
            jackpot_hits=jackpot_hits,
            cumulative_net_pat=cumulative_net,
            rolling_ev_per_spin=round(ev_per_spin, 2),
            rolling_win_rate=round(win_rate, 4),
            net_yield_per_hour_pat=round(net_per_hour, 2),
            observed_jackpot_pool=self.observed_jackpot_pool,
            optimal_timing_offset_ms=best_offset,
            best_bucket_win_rate=round(best_bucket_wr, 4),
            recent_deltas=[r.net_delta_pat for r in all_records[-20:]],
        )

    def export_state_dict(self) -> dict[str, Any]:
        return {
            **asdict(self.get_rolling_ev_metrics()),
            "timing_buckets": self.timing_buckets,
            "heist_state": asdict(self.heist_state),
        }
