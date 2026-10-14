import React, { useState } from "react";
import { orchestrator } from "../services/botStore";
import { EDGE_FEMALE_VOICES, KOKORO_FEMALE_VOICES, COQUI_FEMALE_VOICES } from "../services/constants";
import { Terminal, MessageSquare, Mic, Play, RefreshCw, Trash2, CheckCircle2 } from "lucide-react";

export const InputLines: React.FC = () => {
  const [cmdText, setCmdText] = useState("");
  const [chatText, setChatText] = useState("");
  const [micText, setMicText] = useState("");

  const [engine, setEngine] = useState<"Local GPU (Kokoro)" | "TTS EDGE" | "Coqui (XTTS v2)">("Local GPU (Kokoro)");
  const [selectedVoice, setSelectedVoice] = useState(orchestrator.botSettings.tts_voice);
  const [availableClones, setAvailableClones] = useState(orchestrator.cloneState.availableClones);

  React.useEffect(() => {
    return orchestrator.subscribe(() => {
      setSelectedVoice(orchestrator.botSettings.tts_voice);
      setAvailableClones([...orchestrator.cloneState.availableClones]);
      if (orchestrator.botSettings.tts_voice.startsWith("Active Clone:")) {
        setEngine("Coqui (XTTS v2)");
      }
    });
  }, []);

  const getVoiceOptions = () => {
    if (engine === "Local GPU (Kokoro)") {
      return Object.keys(KOKORO_FEMALE_VOICES);
    }
    if (engine === "Coqui (XTTS v2)") {
      const coquiBase = Object.keys(COQUI_FEMALE_VOICES);
      // Combine base coqui voices with dynamically created clones
      const all = Array.from(new Set([...availableClones, ...coquiBase]));
      return all;
    }
    return Object.keys(EDGE_FEMALE_VOICES);
  };

  const handleEngineChange = (newEngine: "Local GPU (Kokoro)" | "TTS EDGE" | "Coqui (XTTS v2)") => {
    setEngine(newEngine);
    if (newEngine === "Local GPU (Kokoro)") {
      setSelectedVoice("Kokoro Heart");
      orchestrator.botSettings.tts_voice = "Kokoro Heart";
    } else if (newEngine === "Coqui (XTTS v2)") {
      const def = availableClones[availableClones.length - 1] || "Coqui Default (Test Clone)";
      setSelectedVoice(def);
      orchestrator.botSettings.tts_voice = def;
    } else {
      setSelectedVoice("Edge Aria");
      orchestrator.botSettings.tts_voice = "Edge Aria";
    }
  };

  const handleSubmitCmd = (e?: React.FormEvent) => {
    if (e) e.preventDefault();
    if (cmdText.trim()) {
      orchestrator.executeAdminCmd(cmdText);
      setCmdText("");
    }
  };

  const handleSubmitChat = (e?: React.FormEvent) => {
    if (e) e.preventDefault();
    if (chatText.trim()) {
      orchestrator.sendManualChat(chatText);
      setChatText("");
    }
  };

  const handleSubmitMic = (e?: React.FormEvent) => {
    if (e) e.preventDefault();
    if (micText.trim()) {
      orchestrator.speakOnMic(micText, selectedVoice);
      setMicText("");
    }
  };

  return (
    <div className="bg-[#0B1120] border border-[#334155] rounded-md p-2.5 space-y-2 text-xs font-mono shadow-xl">
      {/* LINE 1: Administrator Command Prompt (cmd.exe) Emulator */}
      <form onSubmit={handleSubmitCmd} className="flex flex-wrap items-center gap-2">
        <div className="flex items-center gap-1.5 w-64 text-[#38BDF8] font-bold shrink-0">
          <Terminal className="w-4 h-4 text-sky-400" />
          <span>1) ADMIN CMD LINE (C:\Windows\System32&gt;):</span>
        </div>
        <input
          type="text"
          value={cmdText}
          onChange={(e) => setCmdText(e.target.value)}
          placeholder="Type Windows shell or cmd command (e.g. dir, dxdiag, status)..."
          className="flex-1 min-w-[200px] bg-[#030712] border border-slate-700 rounded px-2.5 py-1 text-[#38BDF8] placeholder-slate-600 focus:outline-none focus:border-sky-500 font-mono"
        />
        <button
          type="submit"
          className="px-3 py-1 rounded bg-[#0284C7] hover:bg-[#38BDF8] text-white font-bold transition-all cursor-pointer shadow-sm active:scale-95 shrink-0"
        >
          Run Admin CMD
        </button>
      </form>

      {/* LINE 2: Talk as Bot in Camfrog Chat */}
      <form onSubmit={handleSubmitChat} className="flex flex-wrap items-center gap-2">
        <div className="flex items-center gap-1.5 w-64 text-[#FBBF24] font-bold shrink-0">
          <MessageSquare className="w-4 h-4 text-amber-400" />
          <span>2) BOT CHAT LINE (Send to Camfrog Chat):</span>
        </div>
        <input
          type="text"
          value={chatText}
          onChange={(e) => setChatText(e.target.value)}
          placeholder="Type message or trigger (!spin, !sheet, !join, !bail, !diss, kaekae)..."
          className="flex-1 min-w-[200px] bg-[#030712] border border-slate-700 rounded px-2.5 py-1 text-[#F8FAFC] placeholder-slate-600 focus:outline-none focus:border-amber-500 font-mono"
        />
        <button
          type="submit"
          className="px-3 py-1 rounded bg-[#F59E0B] hover:bg-[#FBBF24] text-[#090D16] font-bold transition-all cursor-pointer shadow-sm active:scale-95 shrink-0"
        >
          Send as Bot in Chat
        </button>
      </form>

      {/* LINE 3: Special KaeKae_Toad Microphone Broadcast Line */}
      <div className="space-y-1.5 pt-0.5">
        <form onSubmit={handleSubmitMic} className="flex flex-wrap items-center gap-2">
          <div className="flex items-center gap-1.5 w-64 text-[#34D399] font-bold shrink-0">
            <Mic className="w-4 h-4 text-emerald-400" />
            <span>3) SPECIAL MIC LINE (Speak on Mic):</span>
          </div>
          <input
            type="text"
            value={micText}
            onChange={(e) => setMicText(e.target.value)}
            placeholder="Type phrase to broadcast over Camfrog microphone via VB-Cable..."
            className="flex-1 min-w-[180px] bg-[#030712] border border-slate-700 rounded px-2.5 py-1 text-[#34D399] placeholder-slate-600 focus:outline-none focus:border-emerald-500 font-mono"
          />

          {/* Engine Menu */}
          <select
            value={engine}
            onChange={(e) => handleEngineChange(e.target.value as any)}
            className="bg-[#030712] border border-slate-700 rounded px-2 py-1 text-slate-200 font-sans cursor-pointer focus:outline-none"
          >
            <option value="Local GPU (Kokoro)">Local GPU (Kokoro)</option>
            <option value="TTS EDGE">TTS EDGE</option>
            <option value="Coqui (XTTS v2)">Coqui (XTTS v2)</option>
          </select>

          {/* Voice Menu */}
          <select
            value={selectedVoice}
            onChange={(e) => setSelectedVoice(e.target.value)}
            className="bg-[#030712] border border-slate-700 rounded px-2 py-1 text-slate-200 font-sans cursor-pointer focus:outline-none"
          >
            {getVoiceOptions().map((v) => (
              <option key={v} value={v}>
                {v}
              </option>
            ))}
          </select>

          <button
            type="submit"
            className="px-3 py-1 rounded bg-[#10B981] hover:bg-[#34D399] text-[#022C22] font-bold transition-all cursor-pointer shadow-sm active:scale-95 shrink-0"
          >
            🎙️ Speak on Mic (VB-Cable)
          </button>
        </form>

        {/* Coqui Voice Cloning Toolset */}
        <div className="flex flex-wrap items-center gap-2 pl-2 border-t border-slate-800/60 pt-1.5">
          <span className="w-60 font-bold text-[#A78BFA] flex items-center gap-1">
            <span>🧬 COQUI VOICE CLONE:</span>
          </span>

          <button
            onClick={() => orchestrator.coquiSample()}
            className="px-2.5 py-0.5 rounded bg-[#8B5CF6] hover:bg-[#A78BFA] text-white text-[11px] font-bold transition-all cursor-pointer active:scale-95"
          >
            🎙️ Sample
          </button>

          <button
            onClick={() => orchestrator.coquiClone()}
            className="px-2.5 py-0.5 rounded bg-[#6366F1] hover:bg-[#818CF8] text-white text-[11px] font-bold transition-all cursor-pointer active:scale-95"
          >
            🧬 Clone Voice
          </button>

          <button
            onClick={() => orchestrator.coquiDefault()}
            className="px-2.5 py-0.5 rounded bg-[#10B981] hover:bg-[#34D399] text-[#022C22] text-[11px] font-bold transition-all cursor-pointer active:scale-95 flex items-center gap-1"
          >
            <Play className="w-3 h-3 fill-current" />
            <span>Default</span>
          </button>

          <button
            onClick={() => orchestrator.coquiClear()}
            className="px-2.5 py-0.5 rounded bg-[#DC2626] hover:bg-[#EF4444] text-white text-[11px] font-bold transition-all cursor-pointer active:scale-95 flex items-center gap-1"
          >
            <Trash2 className="w-3 h-3" />
            <span>CLR Voice</span>
          </button>

          <span className="text-[10px] text-slate-400 italic">
            Sample → Clone → Default broadcasts the clone; CLR Voice reverts to Coqui Default.
          </span>
        </div>
      </div>
    </div>
  );
};
