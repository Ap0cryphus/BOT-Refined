import React, { useState, useEffect } from "react";
import { orchestrator } from "../services/botStore";
import { Zap, Stethoscope, Crosshair, Mic, Compass, Play, Square, Shield, Dices } from "lucide-react";

interface TopBarProps {
  onOpenWizard: () => void;
  onOpenDiagnostics: () => void;
}

export const TopBar: React.FC<TopBarProps> = ({ onOpenWizard, onOpenDiagnostics }) => {
  const [appMode, setAppMode] = useState(orchestrator.appMode);
  const [autoSpin, setAutoSpin] = useState(orchestrator.autoSpinEnabled);
  const [randomMode, setRandomMode] = useState(orchestrator.randomSpinMode);
  const [calibratingChat, setCalibratingChat] = useState(false);
  const [calibratingTalk, setCalibratingTalk] = useState(false);

  useEffect(() => {
    return orchestrator.subscribe(() => {
      setAppMode(orchestrator.appMode);
      setAutoSpin(orchestrator.autoSpinEnabled);
      setRandomMode(orchestrator.randomSpinMode);
    });
  }, []);

  const handleStartAutoSpin = () => {
    orchestrator.setAutoSpinState(true, randomMode);
  };

  const handleStopAutoSpin = () => {
    orchestrator.setAutoSpinState(false);
  };

  const handleToggleRandom = (e: React.ChangeEvent<HTMLInputElement>) => {
    const checked = e.target.checked;
    setRandomMode(checked);
    orchestrator.randomSpinMode = checked;
    if (autoSpin) {
      orchestrator.setAutoSpinState(true, checked);
    }
  };

  const handleCalibrateChat = () => {
    setCalibratingChat(true);
    orchestrator.emitActionLog("[CALIBRATION 🎯] Move cursor over Camfrog Chat Box... Locking in 3s!");
    setTimeout(() => {
      setCalibratingChat(false);
      orchestrator.setDirectPixels(1536, 1223, orchestrator.calibration.talk_button_screen_pt[0], orchestrator.calibration.talk_button_screen_pt[1]);
    }, 3000);
  };

  const handleCalibrateTalk = () => {
    setCalibratingTalk(true);
    orchestrator.emitActionLog("[CALIBRATION 🎙️] Move cursor over Camfrog Talk Button... Locking in 3s!");
    setTimeout(() => {
      setCalibratingTalk(false);
      orchestrator.setDirectPixels(orchestrator.calibration.chat_input_screen_pt[0], orchestrator.calibration.chat_input_screen_pt[1], 1326, 1182);
    }, 3000);
  };

  const isCloneModeActive = appMode !== "REGULAR";

  return (
    <div className="bg-[#0B0F19] border border-[#EF4444]/60 rounded-md p-1.5 px-3 flex flex-wrap items-center justify-between gap-1.5 shadow-lg">
      <div className="flex flex-wrap items-center gap-1.5">
        {/* ONE-CLICK DEPLOY (REGULAR) */}
        <button
          onClick={() => {
            if (isCloneModeActive) {
              orchestrator.cancelCloneMode();
            } else {
              orchestrator.deployAllOneClick();
            }
          }}
          className={`flex items-center gap-1.5 px-2.5 py-1 text-xs font-bold rounded-md transition-all shadow-sm active:scale-95 cursor-pointer ${
            !isCloneModeActive
              ? "bg-[#EF4444] hover:bg-[#F87171] text-white ring-2 ring-red-400/40"
              : "bg-slate-800 hover:bg-slate-700 text-slate-300 border border-slate-700"
          }`}
        >
          <Zap className="w-3.5 h-3.5" />
          <span>{isCloneModeActive ? "⚡ RESUME REGULAR MODE" : "⚡ ONE-CLICK DEPLOY"}</span>
        </button>

        {/* ONE-CLICK DEPLOY CLONE */}
        <button
          onClick={() => {
            if (isCloneModeActive) {
              orchestrator.cancelCloneMode();
            } else {
              orchestrator.enterCloneMode();
            }
          }}
          className={`flex items-center gap-1.5 px-2.5 py-1 text-xs font-bold rounded-md transition-all shadow-sm active:scale-95 cursor-pointer ${
            isCloneModeActive
              ? "bg-purple-600 hover:bg-purple-500 text-white ring-2 ring-purple-400 animate-pulse font-extrabold"
              : "bg-gradient-to-r from-[#6366F1] to-[#8B5CF6] hover:brightness-110 text-white"
          }`}
        >
          <Mic className="w-3.5 h-3.5" />
          <span>{isCloneModeActive ? "🛑 CANCEL CLONE MODE" : "🎙️ ONE-CLICK DEPLOY CLONE"}</span>
        </button>

        {/* RUN FULL DIAGNOSTICS */}
        <button
          onClick={() => {
            orchestrator.runFullDiagnostics();
            onOpenDiagnostics();
          }}
          className="flex items-center gap-1.5 px-2.5 py-1 text-xs font-bold rounded-md bg-[#8B5CF6] hover:bg-[#A78BFA] text-white transition-all shadow-sm active:scale-95 cursor-pointer"
        >
          <Stethoscope className="w-3.5 h-3.5" />
          <span>🩺 RUN FULL DIAGNOSTICS</span>
        </button>

        {/* CALIBRATE CHAT (3s) */}
        <button
          onClick={handleCalibrateChat}
          className={`flex items-center gap-1 px-2 py-1 text-xs font-bold rounded-md transition-all shadow-sm cursor-pointer ${
            calibratingChat
              ? "bg-amber-400 text-black animate-pulse"
              : "bg-[#F59E0B] hover:bg-[#FBBF24] text-[#090D16]"
          }`}
        >
          <Crosshair className="w-3.5 h-3.5" />
          <span>{calibratingChat ? "🎯 LOCKING (3s)..." : "🎯 CALIBRATE CHAT (3s)"}</span>
        </button>

        {/* CALIBRATE TALK (3s) */}
        <button
          onClick={handleCalibrateTalk}
          className={`flex items-center gap-1 px-2 py-1 text-xs font-bold rounded-md transition-all shadow-sm cursor-pointer ${
            calibratingTalk
              ? "bg-emerald-400 text-black animate-pulse"
              : "bg-[#10B981] hover:bg-[#34D399] text-[#022C22]"
          }`}
        >
          <Mic className="w-3.5 h-3.5" />
          <span>{calibratingTalk ? "🎙️ LOCKING (3s)..." : "🎙️ CALIBRATE TALK (3s)"}</span>
        </button>

        {/* WIZARD */}
        <button
          onClick={onOpenWizard}
          className="flex items-center gap-1 px-2 py-1 text-xs font-bold rounded-md bg-[#0284C7] hover:bg-[#38BDF8] text-white transition-all shadow-sm cursor-pointer"
        >
          <Compass className="w-3.5 h-3.5" />
          <span>🧭 WIZARD</span>
        </button>

        {/* !SPIN ONCE */}
        <button
          onClick={() => orchestrator.stepSpinOnce()}
          className="flex items-center gap-1 px-2.5 py-1 text-xs font-bold rounded-md bg-[#10B981] hover:bg-[#34D399] text-[#022C22] transition-all shadow-sm cursor-pointer active:scale-95"
        >
          <Play className="w-3.5 h-3.5 fill-current" />
          <span>🎰 !SPIN ONCE</span>
        </button>

        {/* START AUTO-SPIN */}
        <button
          onClick={handleStartAutoSpin}
          className={`px-2.5 py-1 text-xs font-bold rounded-md transition-all shadow-sm cursor-pointer ${
            autoSpin
              ? "bg-[#10B981] text-[#022C22] shadow-emerald-500/20"
              : "bg-[#059669] hover:bg-[#10B981] text-white"
          }`}
        >
          <span>{autoSpin ? `🎰 AUTO-SPIN: ON (${randomMode ? "1-3m RND" : "20.2s"})` : "🎰 START AUTO-SPIN"}</span>
        </button>

        {/* AUTO-SPIN: OFF BUTTON */}
        <button
          onClick={handleStopAutoSpin}
          className={`px-2.5 py-1 text-xs font-bold rounded-md transition-all shadow-sm cursor-pointer ${
            !autoSpin
              ? "bg-[#1E293B] text-[#94A3B8] border border-slate-700"
              : "bg-[#B91C1C] hover:bg-[#EF4444] text-white shadow-red-500/30"
          }`}
        >
          <span>{autoSpin ? "🛑 SET AUTO-SPIN: OFF" : "🛑 AUTO-SPIN: OFF"}</span>
        </button>

        {/* 1-3m Random Checkbox */}
        <label className="flex items-center gap-1.5 text-xs font-bold text-[#FBBF24] bg-[#0B0F19] px-2 py-1 rounded border border-slate-800 cursor-pointer select-none">
          <input
            type="checkbox"
            checked={randomMode}
            onChange={handleToggleRandom}
            className="rounded border-slate-700 bg-slate-900 text-amber-500 focus:ring-0 cursor-pointer"
          />
          <Dices className="w-3.5 h-3.5 inline text-amber-400" />
          <span>🎲 1–3m Random</span>
        </label>
      </div>

      <div className="flex items-center gap-1.5 ml-auto">
        {/* STOP ALL */}
        <button
          onClick={() => orchestrator.stopAll()}
          className="flex items-center gap-1 px-3 py-1 text-xs font-bold rounded-md bg-[#DC2626] hover:bg-[#EF4444] text-white transition-all shadow-sm cursor-pointer"
        >
          <Square className="w-3.5 h-3.5 fill-current" />
          <span>🚨 STOP ALL</span>
        </button>

        {/* ADMIN */}
        <div className="flex items-center gap-1 px-2 py-1 text-xs font-bold rounded-md bg-[#7C3AED]/20 border border-[#7C3AED]/50 text-[#C4B5FD]">
          <Shield className="w-3.5 h-3.5 text-purple-400" />
          <span>🛡️ ADMIN (ACTIVE)</span>
        </div>
      </div>
    </div>
  );
};
