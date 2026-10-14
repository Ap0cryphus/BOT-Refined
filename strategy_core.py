"""
strategy_core.py — Task 3: PepeFrog Cross-Game, Heist Character Builder & Spin Timing Engine
============================================================================================

Evaluates live platform mechanics across `publicaccess.tv` (PepeFrog streaming bot game in Camfrog)
to maximize total wallet capital, learn optimal `!spin` timing windows, and build the strongest
Grand Theft Frogger (`!heist` / `!sheet`) character:

1. `!spin` (Wheel of Misfortune & Timing Phase Optimizer):
   - Flat base bet constraint: `5,000 PAT` per spin.
   - Adaptive Timing Optimizer: Tests spin intervals (`20.15s`, `20.20s`, `20.28s`, `20.36s`, `20.45s`)
     to lock onto the server tick phase producing the highest win percentage and 1-in-3,000 Golden Slice
     Jackpot hits (capped at `5,000,000 PAT`).
   - Conditional Micro-Bet Protocol when jackpot pool is `< 1,750,000 PAT`.

2. `!heist` & Strongest Character Sheet Builder (`publicaccess.tv/help#cat-heists`):
   - Evaluates the 6 D&D stats (`STR`, `DEX`, `CON`, `INT`, `WIS`, `CHA`) on `!sheet`.
   - Identifies the weakest stat to raise with `!allot <stat>` (free stat point every 10 levels)
     or `!buy` stat-rescue consumables (`breaching` STR, `lockpick` DEX, `painkillers` CON,
     `hacking` INT, `scanner` WIS, `badge` CHA).
   - Uses rare `💍 Kingpin's Ring` (`!ring <stat>`) on the primary class/Mastermind stat up to 20,
     and `🎲 Loaded Dice` (`!reroll <stat>`) on any stat `<= 9`.
   - Evaluates heist jobs (`!heist store`, `!heist casino`, `!heist convoy`, `!heist bank`) and
     computes whether to `!bail` at the final pre-vault-door window (Round 9/9 on Casino, Round 11/11
     on Federal Reserve Bank) or push the door when insured with `⚖️ Good Lawyer` + `🏁 Ghost Plates`.

3. `!beg` (Automated Safety Check Loop):
   - Triggers when wallet balance dips below `5,000 PAT` (`0–10,000 PAT` payout, strict 3-hour cooldown).

4. `!lotto` & Multi-Game Evaluators (`!bingo`, `!trivia`, `!showdown`, `!arena`, `!brawl`, `!duel`, `!bj`, `!holdem`):
   - Evaluates weekly Sunday 9 PM ET `!lotto` tickets (`1,000 PAT`), live `!bingo` calls, `!showdown`
     optimal bisection (`!guess 5000`), and PvP `!arena` / `!brawl` entry when character sheet power is high.
"""

from __future__ import annotations

import time
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from typing import Any


# Core Platform Constants (publicaccess.tv PepeFrog Economy)
SPIN_FLAT_COST_PAT: int = 5_000
SPIN_COOLDOWN_SECONDS: float = 20.2  # Base 20.0s server constraint + adaptive phase offset
RANDOM_SPIN_MIN_SECONDS: float = 60.0   # 1 minute minimum random spin interval
RANDOM_SPIN_MAX_SECONDS: float = 180.0  # 3 minutes maximum random spin interval
JACKPOT_POOL_CAP_PAT: int = 5_000_000
JACKPOT_HIT_PROBABILITY: float = 0.0005  # 0.05% chance per spin (1-in-2,000 to 1-in-3,000 range)
LOW_JACKPOT_THRESHOLD_PAT: int = 1_750_000

BEG_MIN_PAYOUT_PAT: int = 0
BEG_MAX_PAYOUT_PAT: int = 10_000
BEG_EXPECTED_PAYOUT_PAT: float = 5_000.0
BEG_COOLDOWN_SECONDS: float = 3 * 3600.0  # Strict 3-hour cooldown (10,800s)

LOTTO_TICKET_COST_PAT: int = 1_000
LOTTO_DRAW_SCHEDULE_DESC: str = "Sundays at 9:00 PM ET"

# Stat-rescue item mapping from publicaccess.tv/help#cat-heists
STAT_RESCUE_GEAR_MAP: dict[str, str] = {
    "STR": "breaching",   # 🧨 Breaching Charge (+2 on failed STR check)
    "DEX": "lockpick",    # 🔓 Lockpick (+2 on failed DEX check)
    "CON": "painkillers", # 💉 Painkillers (+2 on failed CON check)
    "INT": "hacking",     # 💻 Hacking Rig (+2 on failed INT check)
    "WIS": "scanner",     # 📡 Police Scanner (+2 on failed WIS check)
    "CHA": "badge",       # 🪪 Fake Badge (+2 on failed CHA check)
}


@dataclass
class SpinTimingRecord:
    """Recorded spin & timing profit entry saved to data/spin_timing_records.csv & .jsonl."""

    spin_id: int
    timestamp_iso: str
    interval_seconds: float
    window_bracket: str  # "60s-90s" | "90s-120s" | "120s-150s" | "150s-180s"
    phase_offset_ms: int
    outcome: str         # "WIN" | "JACKPOT" | "LOSS"
    gross_payout_pat: int
    net_delta_pat: int
    wallet_after_pat: int
    jackpot_pool_pat: int


def classify_spin_window_bracket(interval_seconds: float) -> str:
    """Classify a 1-3 minute (60s..180s) spin delay into a 30-second profit analytics bracket."""
    if interval_seconds < 90.0:
        return "60s-90s (1.0m-1.5m)"
    if interval_seconds < 120.0:
        return "90s-120s (1.5m-2.0m)"
    if interval_seconds < 150.0:
        return "120s-150s (2.0m-2.5m)"
    return "150s-180s (2.5m-3.0m)"


@dataclass
class StrategyDecision:
    """Actionable output from the PepeFrog cross-game strategic decision tree."""

    command: str                   # "!spin" | "!beg" | "!lotto" | "!bail" | "!heist ..." | "HOLD"
    mode_flag: str                 # "STANDARD_SPIN" | "JACKPOT_HUNT" | "PITY_SURGE" | "MICRO_BET_PROTOCOL" | "SAFETY_BEG" | "LOTTO_ALLOCATION" | "HEIST_OPTIMIZER" | "COOLDOWN_WAIT"
    expected_value_pat: float
    rationale: str
    wallet_balance_pat: int
    jackpot_pool_pat: int
    consecutive_losses: int
    pity_safety_net_active: bool
    beg_cooldown_remaining_s: float
    spin_cooldown_remaining_s: float
    recommended_spin_interval_s: float = 20.200


@dataclass
class HeistCharacterAdvisor:
    """Analyzes the player's 6 D&D stats, relics, and gear to create the strongest character in PepeFrog."""

    stats: dict[str, int] = field(
        default_factory=lambda: {"STR": 14, "DEX": 16, "CON": 15, "INT": 18, "WIS": 14, "CHA": 13}
    )
    unspent_points: int = 0
    character_class: str = "Mastermind"
    relics: list[str] = field(default_factory=lambda: ["Blueprints", "Kingpin's Ring"])
    gear: list[str] = field(
        default_factory=lambda: ["Good Lawyer", "Ghost Plates", "Schematics", "Lockpick", "Hacking Rig"]
    )

    @property
    def total_stat_power(self) -> int:
        return sum(self.stats.values())

    @property
    def weakest_stat(self) -> tuple[str, int]:
        return min(self.stats.items(), key=lambda kv: kv[1])

    @property
    def strongest_stat(self) -> tuple[str, int]:
        return max(self.stats.items(), key=lambda kv: kv[1])

    def recommend_character_upgrade_command(self) -> tuple[str, str]:
        """Return `(command, explanation)` to build the strongest heist character in PepeFrog."""
        weak_stat, weak_val = self.weakest_stat
        strong_stat, strong_val = self.strongest_stat

        # 1. If unspent level-up stat points exist, allot to weakest stat to eliminate single-round pinch failures
        if self.unspent_points > 0:
            return (
                f"!allot {weak_stat.lower()}",
                f"Spend available stat point on weakest stat {weak_stat} ({weak_val} -> {weak_val + 1}) to raise survival floor across all heist rounds.",
            )

        # 2. If a stat is critically low (<= 9) and we have Loaded Dice, reroll it
        if weak_val <= 9 and any("dice" in r.lower() for r in self.relics):
            return (
                f"!reroll {weak_stat.lower()}",
                f"{weak_stat} is critically low ({weak_val}); use 🎲 Loaded Dice to reroll {weak_stat} toward 12+.",
            )

        # 3. If we own Kingpin's Ring and our top stat < 20, permanently boost primary stat
        if strong_val < 20 and any("ring" in r.lower() for r in self.relics):
            return (
                f"!ring {strong_stat.lower()}",
                f"Use 💍 Kingpin's Ring on {strong_stat} ({strong_val} -> {strong_val + 1}/20) to maximize Vault Door crack odds.",
            )

        # 4. Recommend specific stat-rescue consumable for weakest stat
        rescue_item = STAT_RESCUE_GEAR_MAP.get(weak_stat, "lockpick")
        return (
            f"!buy {rescue_item} 1",
            f"Equip stat-rescue '{rescue_item}' (+2 on failed {weak_stat} check) + ⚖️ Good Lawyer & 🏁 Ghost Plates for full kit protection.",
        )

    def evaluate_vault_door_vs_bail(
        self,
        *,
        job: str,
        accrued_loot_pat: int,
        vault_balance_pat: int,
        crew_size: int = 3,
    ) -> tuple[str, str]:
        """Decide whether to `!bail` at the final window before the Vault Door or stay to crack the door.
        Per `publicaccess.tv/help#cat-heists`:
        - Casino door opens ~33% solo (higher with crew + Schematics + Uppers); Bank Federal Reserve < 10% solo.
        - Failing the door loses all held loot unless `Good Lawyer` saves 50%.
        - `Ghost Plates` add +20% bonus when you `!bail`.
        """
        has_lawyer = any("lawyer" in g.lower() for g in self.gear)
        has_ghost_plates = any("ghost" in g.lower() for g in self.gear)
        bail_payout = int(accrued_loot_pat * (1.20 if has_ghost_plates else 1.0))

        base_door_prob = 0.12 if job.lower() == "bank" else 0.34
        stat_bonus = max(0.0, (self.total_stat_power - 80) * 0.008)
        crew_bonus = min(0.22, max(0, crew_size - 1) * 0.06)
        door_prob = min(0.75, base_door_prob + stat_bonus + crew_bonus)

        expected_vault_slice = (vault_balance_pat * 0.06) / max(1, crew_size)
        loss_if_fail = int(accrued_loot_pat * (0.50 if has_lawyer else 1.0))
        door_ev = door_prob * (accrued_loot_pat + expected_vault_slice) - (1.0 - door_prob) * loss_if_fail

        if accrued_loot_pat >= 35_000 and bail_payout > door_ev:
            return (
                "!bail",
                f"Final pre-door window: !bail locks in {bail_payout:,} PAT guaranteed (with Ghost Plates +20%) vs risky Door EV ({door_ev:,.0f} PAT at {door_prob*100:.0f}% odds).",
            )
        return (
            "STAY_FOR_DOOR",
            f"Crew power ({self.total_stat_power} stats, Lawyer={has_lawyer}) yields +{door_ev:,.0f} PAT Door EV ({door_prob*100:.0f}% crack odds) vs {bail_payout:,} PAT bail.",
        )


@dataclass
class PityStateArray:
    """Tracks consecutive failure streaks and empirically observed admin Sink Rate safety nets."""

    consecutive_losses: int = 0
    max_loss_streak_observed: int = 0
    pity_trigger_threshold: int = 6
    detected_safety_net_bounces: int = 0
    streak_history: list[int] = field(default_factory=list)
    sink_rate_estimate: float = 0.54  # Baseline house sink rate before jackpot/pity adjustment

    def record_spin_outcome(self, won: bool) -> None:
        if won:
            if self.consecutive_losses >= self.pity_trigger_threshold:
                self.detected_safety_net_bounces += 1
            if self.consecutive_losses > 0:
                self.streak_history.append(self.consecutive_losses)
                if len(self.streak_history) > 100:
                    self.streak_history.pop(0)
            self.consecutive_losses = 0
        else:
            self.consecutive_losses += 1
            if self.consecutive_losses > self.max_loss_streak_observed:
                self.max_loss_streak_observed = self.consecutive_losses

    @property
    def pity_safety_net_active(self) -> bool:
        """Return True when consecutive loss streak reaches or exceeds the Sink Rate safety-net threshold."""
        return self.consecutive_losses >= self.pity_trigger_threshold


class PepeFrogStrategyEngine:
    """Cross-game strategic analysis engine optimizing PAT capital across !spin, !heist, !beg, !lotto, and cat-games."""

    def __init__(
        self,
        *,
        initial_wallet_pat: int = 25_000,
        initial_jackpot_pat: int = 2_500_000,
        lotto_estimated_pool_pat: int = 450_000,
        lotto_estimated_entries: int = 320,
    ) -> None:
        self.wallet_balance_pat: int = max(0, int(initial_wallet_pat))
        self.initial_wallet_pat: int = self.wallet_balance_pat
        self.jackpot_pool_pat: int = min(JACKPOT_POOL_CAP_PAT, max(0, int(initial_jackpot_pat)))
        self.lotto_estimated_pool_pat: int = max(10_000, int(lotto_estimated_pool_pat))
        self.lotto_estimated_entries: int = max(1, int(lotto_estimated_entries))

        self.pity_state = PityStateArray()
        self.heist_advisor = HeistCharacterAdvisor()
        self.last_spin_mono: float = -9999.0
        self.last_beg_mono: float = -99999.0
        self.lotto_tickets_owned: int = 0
        self.total_spins_executed: int = 0
        self.total_begs_executed: int = 0
        self.total_heists_executed: int = 0
        self.optimal_spin_offset_ms: int = 200
        self.last_random_interval_s: float = 95.200
        self.spin_records: list[SpinTimingRecord] = []
        self.window_bracket_stats: dict[str, dict[str, int]] = {
            "60s-90s (1.0m-1.5m)": {"spins": 0, "wins": 0, "jackpots": 0, "net_pat": 0},
            "90s-120s (1.5m-2.0m)": {"spins": 0, "wins": 0, "jackpots": 0, "net_pat": 0},
            "120s-150s (2.0m-2.5m)": {"spins": 0, "wins": 0, "jackpots": 0, "net_pat": 0},
            "150s-180s (2.5m-3.0m)": {"spins": 0, "wins": 0, "jackpots": 0, "net_pat": 0},
        }

    def roll_random_spin_interval_s(
        self,
        *,
        min_s: float = RANDOM_SPIN_MIN_SECONDS,
        max_s: float = RANDOM_SPIN_MAX_SECONDS,
        offset_ms: int | None = None,
    ) -> float:
        """Roll a randomized auto-spin interval between 1 and 3 minutes (60.0s .. 180.0s)
        combined with the learned micro-timing phase offset (+150ms .. +450ms).
        """
        import random as _rnd

        whole_seconds = _rnd.randint(int(min_s), max(int(min_s), int(max_s) - 1))
        ms = self.optimal_spin_offset_ms if offset_ms is None else int(offset_ms)
        interval = round(float(whole_seconds) + (ms / 1000.0), 3)
        self.last_random_interval_s = interval
        return interval

    def record_spin_timing_profit(
        self,
        *,
        interval_seconds: float,
        phase_offset_ms: int,
        won: bool,
        is_jackpot: bool,
        gross_payout_pat: int,
        net_delta_pat: int,
    ) -> SpinTimingRecord:
        """Record a spin timing & profit entry in memory and append to data/spin_timing_records.csv & .jsonl."""
        import csv as _csv
        import json as _json
        from pathlib import Path as _Path

        bracket = classify_spin_window_bracket(interval_seconds)
        b_entry = self.window_bracket_stats.setdefault(
            bracket, {"spins": 0, "wins": 0, "jackpots": 0, "net_pat": 0}
        )
        b_entry["spins"] += 1
        if won:
            b_entry["wins"] += 1
        if is_jackpot:
            b_entry["jackpots"] += 1
        b_entry["net_pat"] += int(net_delta_pat)

        rec = SpinTimingRecord(
            spin_id=len(self.spin_records) + 1,
            timestamp_iso=datetime.now(timezone.utc).isoformat(timespec="seconds"),
            interval_seconds=round(float(interval_seconds), 3),
            window_bracket=bracket,
            phase_offset_ms=int(phase_offset_ms),
            outcome="JACKPOT" if is_jackpot else ("WIN" if won else "LOSS"),
            gross_payout_pat=int(gross_payout_pat),
            net_delta_pat=int(net_delta_pat),
            wallet_after_pat=self.wallet_balance_pat,
            jackpot_pool_pat=self.jackpot_pool_pat,
        )
        self.spin_records.append(rec)
        if len(self.spin_records) > 500:
            self.spin_records.pop(0)

        try:
            data_dir = _Path(__file__).resolve().parent / "data"
            data_dir.mkdir(parents=True, exist_ok=True)
            csv_path = data_dir / "spin_timing_records.csv"
            write_header = not csv_path.exists() or csv_path.stat().st_size == 0
            with csv_path.open("a", newline="", encoding="utf-8") as cf:
                writer = _csv.writer(cf)
                if write_header:
                    writer.writerow([
                        "spin_id",
                        "timestamp_iso",
                        "interval_seconds",
                        "window_bracket",
                        "phase_offset_ms",
                        "outcome",
                        "gross_payout_pat",
                        "net_delta_pat",
                        "wallet_after_pat",
                        "jackpot_pool_pat",
                    ])
                writer.writerow([
                    rec.spin_id,
                    rec.timestamp_iso,
                    f"{rec.interval_seconds:.3f}",
                    rec.window_bracket,
                    rec.phase_offset_ms,
                    rec.outcome,
                    rec.gross_payout_pat,
                    rec.net_delta_pat,
                    rec.wallet_after_pat,
                    rec.jackpot_pool_pat,
                ])
            jsonl_path = data_dir / "spin_timing_records.jsonl"
            with jsonl_path.open("a", encoding="utf-8") as jf:
                jf.write(_json.dumps(asdict(rec)) + "\n")
        except Exception:
            pass

        return rec

    @property
    def best_profit_window_bracket(self) -> str:
        best_b = "90s-120s (1.5m-2.0m)"
        best_net = -10**9
        for b_name, st in self.window_bracket_stats.items():
            if st["spins"] > 0 and st["net_pat"] > best_net:
                best_net = st["net_pat"]
                best_b = b_name
        return best_b

    def beg_cooldown_remaining(self, now_mono: float | None = None) -> float:
        now = time.perf_counter() if now_mono is None else now_mono
        elapsed = now - self.last_beg_mono
        return max(0.0, BEG_COOLDOWN_SECONDS - elapsed)

    def spin_cooldown_remaining(self, now_mono: float | None = None) -> float:
        now = time.perf_counter() if now_mono is None else now_mono
        elapsed = now - self.last_spin_mono
        return max(0.0, SPIN_COOLDOWN_SECONDS - elapsed)

    def compute_spin_expected_value(self) -> float:
        """Calculate the single-spin Expected Value (EV) in PAT based on regular wheel slices + golden Jackpot slice + Pity boost."""
        base_wheel_return = 4_150.0
        capped_pool = float(min(JACKPOT_POOL_CAP_PAT, max(0, self.jackpot_pool_pat)))
        jackpot_ev_contribution = capped_pool * JACKPOT_HIT_PROBABILITY

        pity_bonus = 0.0
        if self.pity_state.pity_safety_net_active:
            excess = min(10, self.pity_state.consecutive_losses - self.pity_state.pity_trigger_threshold + 1)
            pity_bonus = 320.0 * excess

        gross_expected_return = base_wheel_return + jackpot_ev_contribution + pity_bonus
        return round(gross_expected_return - SPIN_FLAT_COST_PAT, 2)

    def compute_lotto_expected_value(self) -> float:
        """Evaluate weekly !lotto ticket (1,000 PAT flat cost, Sundays 9 PM ET) long-tail yield curve."""
        win_prob = 1.0 / float(max(1, self.lotto_estimated_entries + 1))
        gross_ev = self.lotto_estimated_pool_pat * win_prob
        return round(gross_ev - LOTTO_TICKET_COST_PAT, 2)

    def evaluate_next_action(self, now_mono: float | None = None) -> StrategyDecision:
        """Run the cross-game strategic decision tree and return the highest-yield next command."""
        now = time.perf_counter() if now_mono is None else now_mono
        beg_cd = self.beg_cooldown_remaining(now)
        spin_cd = self.spin_cooldown_remaining(now)
        spin_ev = self.compute_spin_expected_value()
        lotto_ev = self.compute_lotto_expected_value()
        pity_active = self.pity_state.pity_safety_net_active
        rec_interval = round(20.0 + (self.optimal_spin_offset_ms / 1000.0), 3)

        # 1. SAFETY CHECK LOOP (!beg): If wallet balance dips below 5,000 PAT spin threshold
        if self.wallet_balance_pat < SPIN_FLAT_COST_PAT:
            if beg_cd <= 0.0:
                return StrategyDecision(
                    command="!beg",
                    mode_flag="SAFETY_BEG",
                    expected_value_pat=BEG_EXPECTED_PAYOUT_PAT,
                    rationale=(
                        f"Wallet ({self.wallet_balance_pat:,} PAT) is below 5,000 PAT spin threshold "
                        "and 3-hour !beg cooldown is clear. Triggering automated !beg safety replenishment."
                    ),
                    wallet_balance_pat=self.wallet_balance_pat,
                    jackpot_pool_pat=self.jackpot_pool_pat,
                    consecutive_losses=self.pity_state.consecutive_losses,
                    pity_safety_net_active=pity_active,
                    beg_cooldown_remaining_s=0.0,
                    spin_cooldown_remaining_s=spin_cd,
                    recommended_spin_interval_s=rec_interval,
                )
            if self.wallet_balance_pat >= LOTTO_TICKET_COST_PAT and self.lotto_tickets_owned == 0 and lotto_ev > -150:
                return StrategyDecision(
                    command="!lotto",
                    mode_flag="LOTTO_ALLOCATION",
                    expected_value_pat=lotto_ev,
                    rationale=(
                        f"Wallet ({self.wallet_balance_pat:,} PAT) cannot fund a 5,000 PAT !spin and !beg is on cooldown "
                        f"({beg_cd/60.0:.1f}m left). Allocating 1,000 PAT into weekly Sunday 9 PM ET !lotto ticket."
                    ),
                    wallet_balance_pat=self.wallet_balance_pat,
                    jackpot_pool_pat=self.jackpot_pool_pat,
                    consecutive_losses=self.pity_state.consecutive_losses,
                    pity_safety_net_active=pity_active,
                    beg_cooldown_remaining_s=beg_cd,
                    spin_cooldown_remaining_s=spin_cd,
                    recommended_spin_interval_s=rec_interval,
                )
            return StrategyDecision(
                command="HOLD",
                mode_flag="COOLDOWN_WAIT",
                expected_value_pat=0.0,
                rationale=(
                    f"Balance ({self.wallet_balance_pat:,} PAT) below 5,000 PAT spin threshold; "
                    f"waiting {beg_cd/60.0:.1f}m for 3-hour !beg cooldown."
                ),
                wallet_balance_pat=self.wallet_balance_pat,
                jackpot_pool_pat=self.jackpot_pool_pat,
                consecutive_losses=self.pity_state.consecutive_losses,
                pity_safety_net_active=pity_active,
                beg_cooldown_remaining_s=beg_cd,
                spin_cooldown_remaining_s=spin_cd,
                recommended_spin_interval_s=rec_interval,
            )

        # 2. RESIDUAL PROFIT !lotto ALLOCATION:
        net_session_profit = self.wallet_balance_pat - self.initial_wallet_pat
        if (
            self.lotto_tickets_owned < 3
            and self.wallet_balance_pat >= SPIN_FLAT_COST_PAT + LOTTO_TICKET_COST_PAT
            and (
                (net_session_profit >= 10_000 and self.lotto_tickets_owned == 0)
                or (self.jackpot_pool_pat < LOW_JACKPOT_THRESHOLD_PAT and lotto_ev > spin_ev and self.lotto_tickets_owned < 2)
            )
        ):
            return StrategyDecision(
                command="!lotto",
                mode_flag="LOTTO_ALLOCATION",
                expected_value_pat=lotto_ev,
                rationale=(
                    f"Allocating 1,000 PAT residual profit into weekly !lotto ({LOTTO_DRAW_SCHEDULE_DESC}) "
                    f"for long-tail yield diversification (Lotto EV: {lotto_ev:+.0f} PAT vs Spin EV: {spin_ev:+.0f} PAT)."
                ),
                wallet_balance_pat=self.wallet_balance_pat,
                jackpot_pool_pat=self.jackpot_pool_pat,
                consecutive_losses=self.pity_state.consecutive_losses,
                pity_safety_net_active=pity_active,
                beg_cooldown_remaining_s=beg_cd,
                spin_cooldown_remaining_s=spin_cd,
                recommended_spin_interval_s=rec_interval,
            )

        # 3. PITY MECHANICS / SINK-RATE SAFETY NET OVERRIDE:
        if pity_active:
            return StrategyDecision(
                command="!spin",
                mode_flag="PITY_SURGE",
                expected_value_pat=spin_ev,
                rationale=(
                    f"Consecutive loss streak ({self.pity_state.consecutive_losses}) reached Sink-Rate Pity threshold "
                    f"(>= {self.pity_state.pity_trigger_threshold}). Executing high-priority !spin ({rec_interval:.3f}s phase) to capture safety-net bounce."
                ),
                wallet_balance_pat=self.wallet_balance_pat,
                jackpot_pool_pat=self.jackpot_pool_pat,
                consecutive_losses=self.pity_state.consecutive_losses,
                pity_safety_net_active=True,
                beg_cooldown_remaining_s=beg_cd,
                spin_cooldown_remaining_s=spin_cd,
                recommended_spin_interval_s=rec_interval,
            )

        # 4. LOW JACKPOT CONDITIONAL MICRO-BET PROTOCOL:
        if self.jackpot_pool_pat < LOW_JACKPOT_THRESHOLD_PAT:
            return StrategyDecision(
                command="!spin",
                mode_flag="MICRO_BET_PROTOCOL",
                expected_value_pat=spin_ev,
                rationale=(
                    f"Jackpot pool ({self.jackpot_pool_pat:,} PAT) is below {LOW_JACKPOT_THRESHOLD_PAT:,} PAT threshold. "
                    f"Micro-Bet Protocol active: pacing minimum-exposure spins ({rec_interval:.3f}s timing phase)."
                ),
                wallet_balance_pat=self.wallet_balance_pat,
                jackpot_pool_pat=self.jackpot_pool_pat,
                consecutive_losses=self.pity_state.consecutive_losses,
                pity_safety_net_active=False,
                beg_cooldown_remaining_s=beg_cd,
                spin_cooldown_remaining_s=spin_cd,
                recommended_spin_interval_s=rec_interval,
            )

        # 5. HIGH JACKPOT HUNT / STANDARD SPIN:
        mode = "JACKPOT_HUNT" if self.jackpot_pool_pat >= 3_500_000 else "STANDARD_SPIN"
        return StrategyDecision(
            command="!spin",
            mode_flag=mode,
            expected_value_pat=spin_ev,
            rationale=(
                f"Golden Jackpot pool at {self.jackpot_pool_pat:,} PAT (cap 5,000,000 PAT) yields "
                f"estimated {spin_ev:+.0f} PAT EV/spin. Deploying 5,000 PAT !spin on {rec_interval:.3f}s learned timing cycle."
            ),
            wallet_balance_pat=self.wallet_balance_pat,
            jackpot_pool_pat=self.jackpot_pool_pat,
            consecutive_losses=self.pity_state.consecutive_losses,
            pity_safety_net_active=False,
            beg_cooldown_remaining_s=beg_cd,
            spin_cooldown_remaining_s=spin_cd,
            recommended_spin_interval_s=rec_interval,
        )

    def record_command_execution(
        self,
        command: str,
        *,
        net_delta_pat: int = 0,
        won: bool | None = None,
        now_mono: float | None = None,
    ) -> None:
        """Update wallet capital, cooldown timers, and pity state array after a command executes."""
        now = time.perf_counter() if now_mono is None else now_mono
        cmd = command.strip().lower()

        if cmd == "!spin":
            self.last_spin_mono = now
            self.total_spins_executed += 1
            self.wallet_balance_pat = max(0, self.wallet_balance_pat + int(net_delta_pat))
            if won is not None:
                self.pity_state.record_spin_outcome(bool(won))
                if not won:
                    self.jackpot_pool_pat = min(JACKPOT_POOL_CAP_PAT, self.jackpot_pool_pat + 2_500)
        elif cmd == "!beg":
            self.last_beg_mono = now
            self.total_begs_executed += 1
            self.wallet_balance_pat = max(0, self.wallet_balance_pat + max(0, int(net_delta_pat)))
        elif cmd.startswith("!lotto"):
            self.lotto_tickets_owned += 1
            self.wallet_balance_pat = max(0, self.wallet_balance_pat - LOTTO_TICKET_COST_PAT)
        elif cmd.startswith("!heist"):
            self.total_heists_executed += 1

    def export_telemetry(self) -> dict[str, Any]:
        decision = self.evaluate_next_action()
        upg_cmd, upg_reason = self.heist_advisor.recommend_character_upgrade_command()
        return {
            "wallet_balance_pat": self.wallet_balance_pat,
            "net_profit_pat": self.wallet_balance_pat - self.initial_wallet_pat,
            "jackpot_pool_pat": self.jackpot_pool_pat,
            "jackpot_cap_pat": JACKPOT_POOL_CAP_PAT,
            "spin_ev_pat": self.compute_spin_expected_value(),
            "lotto_ev_pat": self.compute_lotto_expected_value(),
            "lotto_tickets_owned": self.lotto_tickets_owned,
            "total_spins_executed": self.total_spins_executed,
            "total_begs_executed": self.total_begs_executed,
            "total_heists_executed": self.total_heists_executed,
            "optimal_spin_offset_ms": self.optimal_spin_offset_ms,
            "last_random_interval_s": self.last_random_interval_s,
            "best_profit_window_bracket": self.best_profit_window_bracket,
            "window_bracket_stats": self.window_bracket_stats,
            "recent_spin_records": [asdict(r) for r in self.spin_records[-15:]],
            "pity_state": asdict(self.pity_state),
            "heist_character": {
                **asdict(self.heist_advisor),
                "total_stat_power": self.heist_advisor.total_stat_power,
                "recommended_upgrade_cmd": upg_cmd,
                "recommended_upgrade_reason": upg_reason,
            },
            "next_decision": asdict(decision),
            "updated_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        }
