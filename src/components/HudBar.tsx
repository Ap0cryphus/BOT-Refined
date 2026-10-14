import React, { useState, useEffect } from "react";
import { orchestrator } from "../services/botStore";
import { Radio, Coins, Trophy, Clock, LineChart } from "lucide-react";

export const HudBar: React.FC = () => {
  const [speaker, setSpeaker] = useState(orchestrator.currentSpeaker);
  const [autoSpin, setAutoSpin] = useState(orchestrator.autoSpinEnabled);
  const [randomMode, setRandomMode] = useState(orchestrator.randomSpinMode);
  const [countdown, setCountdown] = useState(orchestrator.nextSpinCountdownS);
  const [wallet, setWallet] = useState(orchestrator.strategy.walletBalancePat);
  const [profit, setProfit] = useState(orchestrator.strategy.walletBalancePat - orchestrator.strategy.initialWalletPat);
  const [jackpot, setJackpot] = useState(orchestrator.strategy.jackpotPoolPat);
  const [spinsCount, setSpinsCount] = useState(orchestrator.strategy.totalSpinsExecuted);
  const [txChat, setTxChat] = useState(orchestrator.botSettings.post_transcripts_to_chat);

  const [appMode, setAppMode] = useState(orchestrator.appMode);
  const [cloneState, setCloneState] = useState(orchestrator.cloneState);

  useEffect(() => {
    return orchestrator.subscribe(() => {
      setAppMode(orchestrator.appMode);
      setCloneState({ ...orchestrator.cloneState });
      setSpeaker(orchestrator.currentSpeaker);
      setAutoSpin(orchestrator.autoSpinEnabled);
      setRandomMode(orchestrator.randomSpinMode);
      setCountdown(orchestrator.nextSpinCountdownS);
      setWallet(orchestrator.strategy.walletBalancePat);
      setProfit(orchestrator.strategy.walletBalancePat - orchestrator.strategy.initialWalletPat);
      setJackpot(orchestrator.strategy.jackpotPoolPat);
      setSpinsCount(orchestrator.strategy.totalSpinsExecuted);
      setTxChat(orchestrator.botSettings.post_transcripts_to_chat);
    });
  }, []);

  let stateBadge = "🟢 KAEKAE LISTENING (AUTO-SPIN: OFF)";
  let badgeColor = "bg-emerald-950/80 text-emerald-400 border-emerald-500/40";

  if (appMode === "CLONE_ARMED") {
    stateBadge = "🎙️ CLONE MODE: ARMED (WAITING FOR SPEAKER)";
    badgeColor = "bg-purple-900 text-purple-200 border-purple-400 font-extrabold animate-pulse";
  } else if (appMode === "CLONE_SAMPLING") {
    stateBadge = `🎙️ HIJACKING AUDIO: ${cloneState.targetSpeaker || "SPEAKER"} (${cloneState.elapsedSeconds}s/4.5s)`;
    badgeColor = "bg-sky-900 text-sky-200 border-sky-400 font-extrabold animate-pulse";
  } else if (appMode === "CLONE_PROCESSING") {
    stateBadge = "🧬 SYNTHESIZING XTTS-V2 EMBEDDING...";
    badgeColor = "bg-amber-900 text-amber-200 border-amber-400 font-extrabold animate-pulse";
  } else if (appMode === "CLONE_READY") {
    stateBadge = `✅ CLONE READY: ${cloneState.lastClonedVoice}`;
    badgeColor = "bg-emerald-600 text-white border-emerald-300 font-extrabold";
  } else if (autoSpin) {
    stateBadge = `🎰 AUTO-SPIN: ON (${randomMode ? "1-3m RND" : "20.2s"})`;
    badgeColor = "bg-emerald-600 text-white border-emerald-300 font-extrabold animate-pulse-subtle";
  }

  return (
    <div className="bg-[#0F172A] border border-slate-800 rounded-md px-3 py-1.5 flex flex-wrap items-center justify-between gap-2 text-xs font-mono shadow-md">
      {/* State & Speaker */}
      <div className="flex flex-wrap items-center gap-2">
        <span className={`px-2 py-0.5 rounded border text-[11px] font-bold ${badgeColor}`}>
          {stateBadge}
        </span>

        <div className="flex items-center gap-1.5 px-2 py-0.5 rounded bg-slate-900 border border-slate-700 text-slate-200">
          <Radio className={`w-3.5 h-3.5 ${speaker ? "text-red-400 animate-ping" : "text-emerald-400"}`} />
          <span>
            🎙️ SPEAKER_ON_MIC:{" "}
            <strong className={speaker ? "text-amber-300 font-bold" : "text-emerald-400"}>
              {speaker || "None (Mic Free)"}
            </strong>
          </span>
          <span className="text-[10px] text-slate-400 ml-1">
            (MicLog: {txChat ? "CHAT-ON" : "SILENT-DB"})
          </span>
        </div>
      </div>

      {/* Financials & Timers */}
      <div className="flex flex-wrap items-center gap-3">
        <div className="flex items-center gap-1 text-slate-300">
          <Coins className="w-3.5 h-3.5 text-amber-400" />
          <span>Wallet:</span>
          <strong className="text-amber-300 font-bold">{wallet.toLocaleString()} PAT</strong>
          <span className={`text-[10px] ${profit >= 0 ? "text-emerald-400" : "text-red-400"}`}>
            ({profit >= 0 ? "+" : ""}{profit.toLocaleString()})
          </span>
        </div>

        <div className="flex items-center gap-1 text-slate-300">
          <Trophy className="w-3.5 h-3.5 text-yellow-400" />
          <span>Jackpot:</span>
          <strong className="text-yellow-300 font-bold">{jackpot.toLocaleString()} PAT</strong>
        </div>

        <div className="flex items-center gap-1 text-slate-300">
          <Clock className="w-3.5 h-3.5 text-sky-400" />
          <span>Next !spin:</span>
          <strong className="text-sky-300 font-bold">{countdown.toFixed(1)}s</strong>
        </div>

        <div className="flex items-center gap-1 text-slate-300">
          <LineChart className="w-3.5 h-3.5 text-purple-400" />
          <span>Spins Analyzed:</span>
          <strong className="text-purple-300 font-bold">{spinsCount}</strong>
        </div>
      </div>
    </div>
  );
};
