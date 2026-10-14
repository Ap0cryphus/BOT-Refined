import React, { useState, useEffect } from "react";
import { orchestrator } from "../services/botStore";
import { Radio, Mic, Cpu, CheckCircle2, XCircle, Volume2, Sparkles } from "lucide-react";

export const CloneStatusRibbon: React.FC = () => {
  const [appMode, setAppMode] = useState(orchestrator.appMode);
  const [cloneState, setCloneState] = useState(orchestrator.cloneState);
  const [speaker, setSpeaker] = useState(orchestrator.currentSpeaker);

  useEffect(() => {
    return orchestrator.subscribe(() => {
      setAppMode(orchestrator.appMode);
      setCloneState({ ...orchestrator.cloneState });
      setSpeaker(orchestrator.currentSpeaker);
    });
  }, []);

  if (appMode === "REGULAR") {
    return null;
  }

  const isArmed = appMode === "CLONE_ARMED";
  const isSampling = appMode === "CLONE_SAMPLING";
  const isProcessing = appMode === "CLONE_PROCESSING";
  const isReady = appMode === "CLONE_READY";

  return (
    <div className="bg-gradient-to-r from-[#200B3B] via-[#0E1528] to-[#1F0D22] border-2 border-purple-500/80 rounded-md p-2.5 px-3 shadow-2xl flex flex-col gap-2 font-mono text-xs animate-in fade-in duration-300">
      {/* Top Banner Row */}
      <div className="flex flex-wrap items-center justify-between gap-2 border-b border-purple-800/40 pb-1.5">
        <div className="flex items-center gap-2">
          <span className="flex h-2.5 w-2.5 relative">
            <span className="animate-ping absolute inline-flex h-full w-full rounded-full bg-purple-400 opacity-75" />
            <span className="relative inline-flex rounded-full h-2.5 w-2.5 bg-purple-500" />
          </span>
          <span className="text-white font-extrabold text-sm tracking-wide flex items-center gap-1.5">
            <Sparkles className="w-4 h-4 text-amber-300 animate-pulse" />
            <span>ONE-CLICK DEPLOY CLONE: ACTIVE PIPELINE</span>
          </span>
          <span className="text-[10px] text-purple-300 bg-purple-950/80 px-2 py-0.5 rounded border border-purple-700/60 font-bold">
            SAFE ISOLATION ACTIVE
          </span>
        </div>

        {/* Abort / Cancel button */}
        <div className="flex items-center gap-2">
          {isArmed && (
            <button
              onClick={() => orchestrator.simulateSpeakerMicGrab(speaker || "Rosie")}
              className="px-2.5 py-1 text-[11px] font-bold rounded bg-[#8B5CF6] hover:bg-[#A78BFA] text-white transition-all cursor-pointer shadow-sm active:scale-95 flex items-center gap-1"
            >
              <Volume2 className="w-3.5 h-3.5" />
              <span>Simulate Mic Grab ({speaker || "Rosie"})</span>
            </button>
          )}

          <button
            onClick={() => orchestrator.cancelCloneMode()}
            className="flex items-center gap-1 px-3 py-1 text-xs font-bold rounded bg-rose-700 hover:bg-rose-600 text-white transition-all cursor-pointer shadow-md active:scale-95"
          >
            <XCircle className="w-3.5 h-3.5" />
            <span>CANCEL CLONE (RETURN TO REGULAR)</span>
          </button>
        </div>
      </div>

      {/* 4 Pipeline Stages */}
      <div className="grid grid-cols-1 sm:grid-cols-2 md:grid-cols-4 gap-2 text-center text-[11px]">
        {/* Stage 1: Armed */}
        <div
          className={`p-2 rounded border flex flex-col items-center justify-center gap-0.5 transition-all ${
            isArmed
              ? "bg-purple-950/90 border-purple-400 text-purple-200 shadow-lg shadow-purple-500/20 font-bold"
              : isSampling || isProcessing || isReady
              ? "bg-slate-900/60 border-emerald-500/40 text-emerald-300"
              : "bg-slate-900/40 border-slate-800 text-slate-500"
          }`}
        >
          <div className="flex items-center gap-1">
            <Radio className={`w-3.5 h-3.5 ${isArmed ? "animate-pulse text-amber-300" : ""}`} />
            <span>1. LISTENER ARMED</span>
          </div>
          <span className="text-[10px] text-slate-300">
            {isArmed
              ? speaker
                ? `Speaker '${speaker}' on mic!`
                : "Waiting for speaker on mic..."
              : "Speaker detected ✅"}
          </span>
        </div>

        {/* Stage 2: Audio Hijack */}
        <div
          className={`p-2 rounded border flex flex-col items-center justify-center gap-0.5 transition-all ${
            isSampling
              ? "bg-sky-950/90 border-sky-400 text-sky-200 shadow-lg shadow-sky-500/20 font-bold animate-pulse-subtle"
              : isProcessing || isReady
              ? "bg-slate-900/60 border-emerald-500/40 text-emerald-300"
              : "bg-slate-900/40 border-slate-800 text-slate-500"
          }`}
        >
          <div className="flex items-center gap-1">
            <Mic className={`w-3.5 h-3.5 ${isSampling ? "text-sky-300 animate-bounce" : ""}`} />
            <span>2. AUDIO HIJACK (4.5s)</span>
          </div>
          <span className="text-[10px] text-slate-300">
            {isSampling
              ? `Sampling '${cloneState.targetSpeaker}' (${cloneState.elapsedSeconds}s / 4.5s)`
              : isProcessing || isReady
              ? `Sampled '${cloneState.targetSpeaker}' (24kHz) ✅`
              : "Awaiting mic grab"}
          </span>
        </div>

        {/* Stage 3: XTTS-v2 Synthesis */}
        <div
          className={`p-2 rounded border flex flex-col items-center justify-center gap-0.5 transition-all ${
            isProcessing
              ? "bg-amber-950/90 border-amber-400 text-amber-200 shadow-lg shadow-amber-500/20 font-bold"
              : isReady
              ? "bg-slate-900/60 border-emerald-500/40 text-emerald-300"
              : "bg-slate-900/40 border-slate-800 text-slate-500"
          }`}
        >
          <div className="flex items-center gap-1">
            <Cpu className={`w-3.5 h-3.5 ${isProcessing ? "text-amber-300 animate-spin" : ""}`} />
            <span>3. XTTS-V2 EMBEDDING</span>
          </div>
          <span className="text-[10px] text-slate-300">
            {isProcessing ? "Extracting 512-dim latent vector..." : isReady ? "Embedding verified ✅" : "Pending sample"}
          </span>
        </div>

        {/* Stage 4: Deployed & Return */}
        <div
          className={`p-2 rounded border flex flex-col items-center justify-center gap-0.5 transition-all ${
            isReady
              ? "bg-emerald-950/90 border-emerald-400 text-emerald-200 shadow-lg shadow-emerald-500/20 font-bold"
              : "bg-slate-900/40 border-slate-800 text-slate-500"
          }`}
        >
          <div className="flex items-center gap-1">
            <CheckCircle2 className="w-3.5 h-3.5 text-emerald-400" />
            <span>4. LOAD & RESUME</span>
          </div>
          <span className="text-[10px] text-slate-300">
            {isReady ? `Loaded '${cloneState.lastClonedVoice}'` : "Restores Regular Mode"}
          </span>
        </div>
      </div>

      {/* Live Sample Progress Bar */}
      {isSampling && (
        <div className="w-full bg-slate-950 rounded-full h-2 overflow-hidden border border-sky-800/60">
          <div
            className="bg-gradient-to-r from-sky-500 via-indigo-500 to-emerald-400 h-full transition-all duration-200 ease-out"
            style={{ width: `${cloneState.sampleProgress}%` }}
          />
        </div>
      )}
    </div>
  );
};
