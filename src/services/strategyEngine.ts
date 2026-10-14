import {
  SPIN_FLAT_COST_PAT,
  SPIN_COOLDOWN_SECONDS,
  RANDOM_SPIN_MIN_SECONDS,
  RANDOM_SPIN_MAX_SECONDS,
  JACKPOT_POOL_CAP_PAT,
  JACKPOT_HIT_PROBABILITY,
  LOW_JACKPOT_THRESHOLD_PAT,
  BEG_EXPECTED_PAYOUT_PAT,
  BEG_COOLDOWN_SECONDS,
  LOTTO_TICKET_COST_PAT,
  LOTTO_DRAW_SCHEDULE_DESC,
  STAT_RESCUE_GEAR_MAP,
} from "./constants";
import {
  SpinTimingRecord,
  StrategyDecision,
  HeistCharacter,
  PityState,
  WindowBracketStats,
} from "../types";

export function classifySpinWindowBracket(intervalSeconds: number): string {
  if (intervalSeconds < 90.0) return "60s-90s (1.0m-1.5m)";
  if (intervalSeconds < 120.0) return "90s-120s (1.5m-2.0m)";
  if (intervalSeconds < 150.0) return "120s-150s (2.0m-2.5m)";
  return "150s-180s (2.5m-3.0m)";
}

export class StrategyEngine {
  walletBalancePat = 25_000;
  initialWalletPat = 25_000;
  jackpotPoolPat = 2_850_000;
  lottoEstimatedPoolPat = 450_000;
  lottoEstimatedEntries = 320;
  lottoTicketsOwned = 0;

  totalSpinsExecuted = 0;
  totalBegsExecuted = 0;
  totalHeistsExecuted = 0;

  optimalSpinOffsetMs = 200;
  lastRandomIntervalS = 95.2;

  lastSpinTimestamp = 0;
  lastBegTimestamp = 0;

  pityState: PityState = {
    consecutive_losses: 0,
    max_loss_streak_observed: 3,
    pity_trigger_threshold: 6,
    detected_safety_net_bounces: 0,
    pity_safety_net_active: false,
    sink_rate_estimate: 0.54,
  };

  heistCharacter: HeistCharacter = {
    stats: { STR: 14, DEX: 16, CON: 15, INT: 18, WIS: 14, CHA: 13 },
    unspent_points: 0,
    character_class: "Mastermind",
    relics: ["Blueprints", "Kingpin's Ring"],
    gear: ["Good Lawyer", "Ghost Plates", "Schematics", "Lockpick", "Hacking Rig"],
    total_stat_power: 90,
  };

  spinRecords: SpinTimingRecord[] = [];

  windowBracketStats: WindowBracketStats = {
    "60s-90s (1.0m-1.5m)": { spins: 0, wins: 0, jackpots: 0, net_pat: 0 },
    "90s-120s (1.5m-2.0m)": { spins: 0, wins: 0, jackpots: 0, net_pat: 0 },
    "120s-150s (2.0m-2.5m)": { spins: 0, wins: 0, jackpots: 0, net_pat: 0 },
    "150s-180s (2.5m-3.0m)": { spins: 0, wins: 0, jackpots: 0, net_pat: 0 },
  };

  constructor() {
    this.updateHeistDerived();
  }

  updateHeistDerived() {
    const s = this.heistCharacter.stats;
    this.heistCharacter.total_stat_power = s.STR + s.DEX + s.CON + s.INT + s.WIS + s.CHA;
    const { cmd, reason } = this.recommendCharacterUpgrade();
    this.heistCharacter.recommended_upgrade_cmd = cmd;
    this.heistCharacter.recommended_upgrade_reason = reason;
  }

  getWeakestStat(): [string, number] {
    const entries = Object.entries(this.heistCharacter.stats);
    entries.sort((a, b) => a[1] - b[1]);
    return [entries[0][0], entries[0][1]];
  }

  getStrongestStat(): [string, number] {
    const entries = Object.entries(this.heistCharacter.stats);
    entries.sort((a, b) => b[1] - a[1]);
    return [entries[0][0], entries[0][1]];
  }

  recommendCharacterUpgrade(): { cmd: string; reason: string } {
    const [weakStat, weakVal] = this.getWeakestStat();
    const [strongStat, strongVal] = this.getStrongestStat();

    if (this.heistCharacter.unspent_points > 0) {
      return {
        cmd: `!allot ${weakStat.toLowerCase()}`,
        reason: `Spend available stat point on weakest stat ${weakStat} (${weakVal} -> ${weakVal + 1}) to raise survival floor across all heist rounds.`,
      };
    }

    if (weakVal <= 9 && this.heistCharacter.relics.some((r) => r.toLowerCase().includes("dice"))) {
      return {
        cmd: `!reroll ${weakStat.toLowerCase()}`,
        reason: `${weakStat} is critically low (${weakVal}); use 🎲 Loaded Dice to reroll ${weakStat} toward 12+.`,
      };
    }

    if (strongVal < 20 && this.heistCharacter.relics.some((r) => r.toLowerCase().includes("ring"))) {
      return {
        cmd: `!ring ${strongStat.toLowerCase()}`,
        reason: `Use 💍 Kingpin's Ring on ${strongStat} (${strongVal} -> ${strongVal + 1}/20) to maximize Vault Door crack odds.`,
      };
    }

    const rescueItem = STAT_RESCUE_GEAR_MAP[weakStat] || "lockpick";
    return {
      cmd: `!buy ${rescueItem} 1`,
      reason: `Equip stat-rescue '${rescueItem}' (+2 on failed ${weakStat} check) + ⚖️ Good Lawyer & 🏁 Ghost Plates for full kit protection.`,
    };
  }

  evaluateVaultDoorVsBail(job: string, accruedLootPat: number, vaultBalancePat: number, crewSize = 3): { action: "!bail" | "STAY_FOR_DOOR"; reason: string; crackProb: number; bailPayout: number; doorEv: number } {
    const hasLawyer = this.heistCharacter.gear.some((g) => g.toLowerCase().includes("lawyer"));
    const hasGhostPlates = this.heistCharacter.gear.some((g) => g.toLowerCase().includes("ghost"));
    const bailPayout = Math.floor(accruedLootPat * (hasGhostPlates ? 1.20 : 1.0));

    const baseDoorProb = job.toLowerCase() === "bank" ? 0.12 : 0.34;
    const statBonus = Math.max(0.0, (this.heistCharacter.total_stat_power - 80) * 0.008);
    const crewBonus = Math.min(0.22, Math.max(0, crewSize - 1) * 0.06);
    const crackProb = Math.min(0.75, baseDoorProb + statBonus + crewBonus);

    const expectedVaultSlice = (vaultBalancePat * 0.06) / Math.max(1, crewSize);
    const lossIfFail = Math.floor(accruedLootPat * (hasLawyer ? 0.50 : 1.0));
    const doorEv = Math.round(crackProb * (accruedLootPat + expectedVaultSlice) - (1.0 - crackProb) * lossIfFail);

    if (accruedLootPat >= 35_000 && bailPayout > doorEv) {
      return {
        action: "!bail",
        reason: `Final pre-door window: !bail locks in ${bailPayout.toLocaleString()} PAT guaranteed (with Ghost Plates +20%) vs risky Door EV (${doorEv.toLocaleString()} PAT at ${(crackProb * 100).toFixed(0)}% odds).`,
        crackProb,
        bailPayout,
        doorEv,
      };
    }

    return {
      action: "STAY_FOR_DOOR",
      reason: `Crew power (${this.heistCharacter.total_stat_power} stats, Lawyer=${hasLawyer}) yields +${doorEv.toLocaleString()} PAT Door EV (${(crackProb * 100).toFixed(0)}% crack odds) vs ${bailPayout.toLocaleString()} PAT bail.`,
      crackProb,
      bailPayout,
      doorEv,
    };
  }

  rollRandomSpinIntervalS(minS = RANDOM_SPIN_MIN_SECONDS, maxS = RANDOM_SPIN_MAX_SECONDS, offsetMs?: number): number {
    const whole = Math.floor(Math.random() * (maxS - minS)) + minS;
    const ms = offsetMs !== undefined ? offsetMs : this.optimalSpinOffsetMs;
    const val = Number((whole + ms / 1000.0).toFixed(3));
    this.lastRandomIntervalS = val;
    return val;
  }

  computeSpinExpectedValue(): number {
    const baseWheelReturn = 4_150.0;
    const cappedPool = Math.min(JACKPOT_POOL_CAP_PAT, Math.max(0, this.jackpotPoolPat));
    const jackpotEv = cappedPool * JACKPOT_HIT_PROBABILITY;

    let pityBonus = 0.0;
    if (this.pityState.pity_safety_net_active) {
      const excess = Math.min(10, this.pityState.consecutive_losses - this.pityState.pity_trigger_threshold + 1);
      pityBonus = 320.0 * excess;
    }

    return Number((baseWheelReturn + jackpotEv + pityBonus - SPIN_FLAT_COST_PAT).toFixed(2));
  }

  computeLottoExpectedValue(): number {
    const winProb = 1.0 / Math.max(1, this.lottoEstimatedEntries + 1);
    const grossEv = this.lottoEstimatedPoolPat * winProb;
    return Number((grossEv - LOTTO_TICKET_COST_PAT).toFixed(2));
  }

  evaluateNextAction(): StrategyDecision {
    const now = Date.now() / 1000;
    const begCd = Math.max(0, BEG_COOLDOWN_SECONDS - (now - this.lastBegTimestamp));
    const spinCd = Math.max(0, SPIN_COOLDOWN_SECONDS - (now - this.lastSpinTimestamp));
    const spinEv = this.computeSpinExpectedValue();
    const lottoEv = this.computeLottoExpectedValue();
    const pityActive = this.pityState.pity_safety_net_active;
    const recInterval = Number((20.0 + this.optimalSpinOffsetMs / 1000.0).toFixed(3));

    // 1. Safety check loop (!beg) if wallet dips below 5,000 PAT
    if (this.walletBalancePat < SPIN_FLAT_COST_PAT) {
      if (begCd <= 0.0) {
        return {
          command: "!beg",
          mode_flag: "SAFETY_BEG",
          expected_value_pat: BEG_EXPECTED_PAYOUT_PAT,
          rationale: `Wallet (${this.walletBalancePat.toLocaleString()} PAT) is below 5,000 PAT spin threshold and 3-hour !beg cooldown is clear. Triggering automated !beg safety replenishment.`,
          wallet_balance_pat: this.walletBalancePat,
          jackpot_pool_pat: this.jackpotPoolPat,
          consecutive_losses: this.pityState.consecutive_losses,
          pity_safety_net_active: pityActive,
          beg_cooldown_remaining_s: 0.0,
          spin_cooldown_remaining_s: spinCd,
          recommended_spin_interval_s: recInterval,
        };
      }

      if (this.walletBalancePat >= LOTTO_TICKET_COST_PAT && this.lottoTicketsOwned === 0 && lottoEv > -150) {
        return {
          command: "!lotto",
          mode_flag: "LOTTO_ALLOCATION",
          expected_value_pat: lottoEv,
          rationale: `Wallet (${this.walletBalancePat.toLocaleString()} PAT) cannot fund 5,000 PAT !spin and !beg is on cooldown (${(begCd / 60).toFixed(1)}m left). Allocating 1,000 PAT into Sunday !lotto.`,
          wallet_balance_pat: this.walletBalancePat,
          jackpot_pool_pat: this.jackpotPoolPat,
          consecutive_losses: this.pityState.consecutive_losses,
          pity_safety_net_active: pityActive,
          beg_cooldown_remaining_s: begCd,
          spin_cooldown_remaining_s: spinCd,
          recommended_spin_interval_s: recInterval,
        };
      }

      return {
        command: "HOLD",
        mode_flag: "COOLDOWN_WAIT",
        expected_value_pat: 0.0,
        rationale: `Balance (${this.walletBalancePat.toLocaleString()} PAT) below 5,000 PAT threshold; waiting ${(begCd / 60).toFixed(1)}m for 3-hour !beg cooldown.`,
        wallet_balance_pat: this.walletBalancePat,
        jackpot_pool_pat: this.jackpotPoolPat,
        consecutive_losses: this.pityState.consecutive_losses,
        pity_safety_net_active: pityActive,
        beg_cooldown_remaining_s: begCd,
        spin_cooldown_remaining_s: spinCd,
        recommended_spin_interval_s: recInterval,
      };
    }

    // 2. Residual profit !lotto allocation
    const netSessionProfit = this.walletBalancePat - this.initialWalletPat;
    if (
      this.lottoTicketsOwned < 3 &&
      this.walletBalancePat >= SPIN_FLAT_COST_PAT + LOTTO_TICKET_COST_PAT &&
      ((netSessionProfit >= 10_000 && this.lottoTicketsOwned === 0) ||
        (this.jackpotPoolPat < LOW_JACKPOT_THRESHOLD_PAT && lottoEv > spinEv && this.lottoTicketsOwned < 2))
    ) {
      return {
        command: "!lotto",
        mode_flag: "LOTTO_ALLOCATION",
        expected_value_pat: lottoEv,
        rationale: `Allocating 1,000 PAT residual profit into weekly !lotto (${LOTTO_DRAW_SCHEDULE_DESC}) for long-tail yield diversification (Lotto EV: ${lottoEv > 0 ? "+" : ""}${lottoEv} PAT).`,
        wallet_balance_pat: this.walletBalancePat,
        jackpot_pool_pat: this.jackpotPoolPat,
        consecutive_losses: this.pityState.consecutive_losses,
        pity_safety_net_active: pityActive,
        beg_cooldown_remaining_s: begCd,
        spin_cooldown_remaining_s: spinCd,
        recommended_spin_interval_s: recInterval,
      };
    }

    // 3. Pity mechanics / Sink-Rate safety net
    if (pityActive) {
      return {
        command: "!spin",
        mode_flag: "PITY_SURGE",
        expected_value_pat: spinEv,
        rationale: `Consecutive loss streak (${this.pityState.consecutive_losses}) reached Sink-Rate Pity threshold (>= ${this.pityState.pity_trigger_threshold}). Executing high-priority !spin (${recInterval}s phase) to capture safety-net bounce.`,
        wallet_balance_pat: this.walletBalancePat,
        jackpot_pool_pat: this.jackpotPoolPat,
        consecutive_losses: this.pityState.consecutive_losses,
        pity_safety_net_active: true,
        beg_cooldown_remaining_s: begCd,
        spin_cooldown_remaining_s: spinCd,
        recommended_spin_interval_s: recInterval,
      };
    }

    // 4. Low jackpot conditional micro-bet protocol
    if (this.jackpotPoolPat < LOW_JACKPOT_THRESHOLD_PAT) {
      return {
        command: "!spin",
        mode_flag: "MICRO_BET_PROTOCOL",
        expected_value_pat: spinEv,
        rationale: `Jackpot pool (${this.jackpotPoolPat.toLocaleString()} PAT) is below ${LOW_JACKPOT_THRESHOLD_PAT.toLocaleString()} PAT threshold. Micro-Bet Protocol active: pacing minimum-exposure spins (${recInterval}s timing phase).`,
        wallet_balance_pat: this.walletBalancePat,
        jackpot_pool_pat: this.jackpotPoolPat,
        consecutive_losses: this.pityState.consecutive_losses,
        pity_safety_net_active: false,
        beg_cooldown_remaining_s: begCd,
        spin_cooldown_remaining_s: spinCd,
        recommended_spin_interval_s: recInterval,
      };
    }

    // 5. Standard spin or high jackpot hunt
    const mode = this.jackpotPoolPat >= 3_500_000 ? "JACKPOT_HUNT" : "STANDARD_SPIN";
    return {
      command: "!spin",
      mode_flag: mode,
      expected_value_pat: spinEv,
      rationale: `Golden Jackpot pool at ${this.jackpotPoolPat.toLocaleString()} PAT (cap 5,000,000 PAT) yields estimated ${spinEv > 0 ? "+" : ""}${spinEv} PAT EV/spin. Deploying 5,000 PAT !spin on ${recInterval}s learned timing cycle.`,
      wallet_balance_pat: this.walletBalancePat,
      jackpot_pool_pat: this.jackpotPoolPat,
      consecutive_losses: this.pityState.consecutive_losses,
      pity_safety_net_active: false,
      beg_cooldown_remaining_s: begCd,
      spin_cooldown_remaining_s: spinCd,
      recommended_spin_interval_s: recInterval,
    };
  }

  recordSpinResult(
    intervalSeconds: number,
    phaseOffsetMs: number,
    outcome: "WIN" | "JACKPOT" | "LOSS",
    grossPayoutPat: number,
    netDeltaPat: number
  ): SpinTimingRecord {
    this.totalSpinsExecuted++;
    this.lastSpinTimestamp = Date.now() / 1000;
    this.walletBalancePat = Math.max(0, this.walletBalancePat + netDeltaPat);

    if (outcome === "LOSS") {
      this.pityState.consecutive_losses++;
      if (this.pityState.consecutive_losses > this.pityState.max_loss_streak_observed) {
        this.pityState.max_loss_streak_observed = this.pityState.consecutive_losses;
      }
      this.pityState.pity_safety_net_active =
        this.pityState.consecutive_losses >= this.pityState.pity_trigger_threshold;
      this.jackpotPoolPat = Math.min(JACKPOT_POOL_CAP_PAT, this.jackpotPoolPat + 2_500);
    } else {
      if (this.pityState.consecutive_losses >= this.pityState.pity_trigger_threshold) {
        this.pityState.detected_safety_net_bounces++;
      }
      this.pityState.consecutive_losses = 0;
      this.pityState.pity_safety_net_active = false;
      if (outcome === "JACKPOT") {
        this.jackpotPoolPat = 2_000_000; // Reset pool after jackpot
      }
    }

    const bracket = classifySpinWindowBracket(intervalSeconds);
    const bEntry = this.windowBracketStats[bracket] || { spins: 0, wins: 0, jackpots: 0, net_pat: 0 };
    bEntry.spins++;
    if (outcome === "WIN" || outcome === "JACKPOT") bEntry.wins++;
    if (outcome === "JACKPOT") bEntry.jackpots++;
    bEntry.net_pat += netDeltaPat;
    this.windowBracketStats[bracket] = bEntry;

    const rec: SpinTimingRecord = {
      spin_id: this.spinRecords.length + 1,
      timestamp_iso: new Date().toISOString(),
      interval_seconds: Number(intervalSeconds.toFixed(3)),
      window_bracket: bracket,
      phase_offset_ms: phaseOffsetMs,
      outcome,
      gross_payout_pat: grossPayoutPat,
      net_delta_pat: netDeltaPat,
      wallet_after_pat: this.walletBalancePat,
      jackpot_pool_pat: this.jackpotPoolPat,
    };

    this.spinRecords.unshift(rec);
    if (this.spinRecords.length > 500) {
      this.spinRecords.pop();
    }

    return rec;
  }

  getBestProfitWindowBracket(): string {
    let bestBracket = "90s-120s (1.5m-2.0m)";
    let bestNet = -1_000_000_000;
    for (const [bracket, stats] of Object.entries(this.windowBracketStats)) {
      if (stats.spins > 0 && stats.net_pat > bestNet) {
        bestNet = stats.net_pat;
        bestBracket = bracket;
      }
    }
    return bestBracket;
  }
}
